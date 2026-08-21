"""Tests for deterministic PumpSteer output supervision."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3 import (
    ControlDecision,
    ControlState,
    ReasonCode,
    SafetyPolicy,
)
from custom_components.pumpsteer.v3.control.supervisor import (
    OutputConstraint,
    SupervisorPolicy,
    supervise_output,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
SAFETY = SafetyPolicy(
    minimum_virtual_temperature=-20.0,
    maximum_virtual_temperature=25.0,
    maximum_heating_request=10.0,
    maximum_curtailment=10.0,
)
POLICY = SupervisorPolicy(
    maximum_slew_per_minute=1.0,
    maximum_step=2.0,
    quantum=0.5,
)


def request(
    *, outdoor: float = 0.0, heating: float = 0.0, curtailment: float = 0.0
) -> ControlDecision:
    return ControlDecision.create(
        decided_at=NOW,
        state=ControlState.COMFORT,
        outdoor_temperature=outdoor,
        heating_request=heating,
        curtailment=curtailment,
        reason_codes=[ReasonCode.COMFORT_WITHIN_BAND],
    )


def test_composes_clamps_and_quantizes_in_that_order() -> None:
    result = supervise_output(
        request(outdoor=20.0, curtailment=50.0),
        safety=SAFETY,
        policy=POLICY,
        now=NOW,
    )

    assert result.value == 25.0
    assert result.constraints == (
        OutputConstraint.CURTAILMENT_LIMIT,
        OutputConstraint.ABSOLUTE_MAXIMUM,
    )
    assert ReasonCode.OUTPUT_SATURATED in result.decision.reason_codes


def test_slew_limit_uses_elapsed_time_not_call_count() -> None:
    previous = supervise_output(
        request(outdoor=0.0), safety=SAFETY, policy=POLICY, now=NOW
    )

    result = supervise_output(
        request(outdoor=0.0, curtailment=10.0),
        safety=SAFETY,
        policy=POLICY,
        now=NOW + timedelta(seconds=30),
        previous=previous,
    )

    assert result.value == 0.5
    assert OutputConstraint.SLEW_LIMIT in result.constraints
    assert ReasonCode.OUTPUT_RATE_LIMITED in result.decision.reason_codes


def test_step_limit_caps_long_interval_change() -> None:
    previous = supervise_output(
        request(outdoor=0.0), safety=SAFETY, policy=POLICY, now=NOW
    )

    result = supervise_output(
        request(outdoor=0.0, curtailment=10.0),
        safety=SAFETY,
        policy=POLICY,
        now=NOW + timedelta(minutes=30),
        previous=previous,
    )

    assert result.value == 2.0
    assert OutputConstraint.STEP_LIMIT in result.constraints


def test_critical_failure_actively_bypasses_old_manipulated_output() -> None:
    previous = supervise_output(
        request(outdoor=-5.0, heating=8.0),
        safety=SAFETY,
        policy=POLICY,
        now=NOW,
    )

    result = supervise_output(
        request(outdoor=-5.0, heating=8.0),
        safety=SAFETY,
        policy=POLICY,
        now=NOW + timedelta(seconds=1),
        previous=previous,
        critical_input_valid=False,
        fallback_outdoor_temperature=-5.0,
    )

    assert result.value == -5.0
    assert result.fallback_active
    assert result.apply_physical
    assert OutputConstraint.CRITICAL_INPUT_FALLBACK in result.constraints
    assert OutputConstraint.SLEW_LIMIT not in result.constraints


def test_internal_failure_without_valid_outdoor_uses_known_fallback() -> None:
    result = supervise_output(
        None,
        safety=SAFETY,
        policy=SupervisorPolicy(safe_fallback_temperature=8.0),
        now=NOW,
        internal_failure=True,
    )

    assert result.value == 8.0
    assert result.decision.state is ControlState.FAILSAFE
    assert ReasonCode.INTERNAL_FAILSAFE in result.decision.reason_codes


def test_shadow_returns_same_supervised_value_without_physical_apply() -> None:
    active = supervise_output(
        request(outdoor=3.0, heating=1.2),
        safety=SAFETY,
        policy=POLICY,
        now=NOW,
    )
    shadow = supervise_output(
        request(outdoor=3.0, heating=1.2),
        safety=SAFETY,
        policy=POLICY,
        now=NOW,
        shadow=True,
    )

    assert shadow.value == active.value
    assert not shadow.apply_physical
    assert ReasonCode.SHADOW_MODE in shadow.decision.reason_codes


def test_rejects_time_going_backwards() -> None:
    previous = supervise_output(request(), safety=SAFETY, policy=POLICY, now=NOW)

    with pytest.raises(ValueError, match="earlier"):
        supervise_output(
            request(curtailment=1.0),
            safety=SAFETY,
            policy=POLICY,
            now=NOW - timedelta(seconds=1),
            previous=previous,
        )
