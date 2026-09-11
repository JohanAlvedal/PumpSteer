"""Contract tests for automatic, comfort-bounded V3 preheat planning."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3 import (
    ComfortPolicy,
    ControlState,
    Observation,
    ReasonCode,
    SafetyPolicy,
    SensorReading,
    Unit,
)
from custom_components.pumpsteer.v3.control.engine import ControlEngine, EngineState
from custom_components.pumpsteer.v3.control.preheat import (
    PreheatContext,
    PreheatReason,
    plan_automatic_preheat,
)
from custom_components.pumpsteer.v3.pricing import PriceBand


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def observation(indoor: float = 21.3) -> Observation:
    return Observation(
        captured_at=NOW,
        indoor=SensorReading(indoor, NOW, Unit.CELSIUS, "sensor.indoor"),
        outdoor=SensorReading(-5.0, NOW, Unit.CELSIUS, "sensor.outdoor"),
    )


def context(
    *,
    band: PriceBand = PriceBand.CHEAP,
    predicted_min: float | None = 20.0,
    authorized: bool = True,
    until: timedelta = timedelta(hours=2),
) -> PreheatContext:
    return PreheatContext(
        current_price_band=band,
        time_until_expensive=until,
        expensive_duration=timedelta(hours=2),
        predicted_min_indoor_temperature=predicted_min,
        prediction_authorized=authorized,
    )


def test_cheap_electricity_alone_never_authorizes_preheat() -> None:
    plan = plan_automatic_preheat(
        observation=observation(),
        comfort_policy=ComfortPolicy(),
        saving_level=3,
        context=context(predicted_min=None, authorized=False),
    )

    assert not plan.active
    assert plan.reason is PreheatReason.PREDICTION_UNAVAILABLE
    assert plan.target_lift_c == 0.0


def test_authorized_predicted_comfort_risk_enables_bounded_preheat() -> None:
    policy = ComfortPolicy(
        target_temperature=21.0, minimum_temperature=19.5, maximum_temperature=23.0
    )
    plan = plan_automatic_preheat(
        observation=observation(21.3),
        comfort_policy=policy,
        saving_level=3,
        context=context(predicted_min=20.0, authorized=True),
    )

    assert plan.active
    assert plan.reason is PreheatReason.PREHEAT_REQUIRED
    assert plan.effective_target_temperature == pytest.approx(21.8)
    assert plan.target_lift_c == pytest.approx(0.8)
    assert plan.effective_target_temperature <= policy.maximum_temperature


def test_house_already_warm_blocks_extra_heating() -> None:
    plan = plan_automatic_preheat(
        observation=observation(21.9),
        comfort_policy=ComfortPolicy(),
        saving_level=5,
        context=context(predicted_min=19.5, authorized=True),
    )

    assert not plan.active
    assert plan.reason is PreheatReason.HOUSE_ALREADY_WARM


def test_saving_level_zero_disables_preheat_even_with_full_context() -> None:
    plan = plan_automatic_preheat(
        observation=observation(),
        comfort_policy=ComfortPolicy(),
        saving_level=0,
        context=context(),
    )

    assert not plan.active
    assert plan.reason is PreheatReason.SAVING_DISABLED


def test_preheat_requires_a_cheap_current_period() -> None:
    plan = plan_automatic_preheat(
        observation=observation(),
        comfort_policy=ComfortPolicy(),
        saving_level=3,
        context=context(band=PriceBand.NORMAL),
    )

    assert not plan.active
    assert plan.reason is PreheatReason.PRICE_NOT_CHEAP


def test_preheat_never_starts_outside_six_hour_lookahead() -> None:
    plan = plan_automatic_preheat(
        observation=observation(),
        comfort_policy=ComfortPolicy(),
        saving_level=3,
        context=context(until=timedelta(hours=6, minutes=1)),
    )

    assert not plan.active
    assert plan.reason is PreheatReason.OUTSIDE_LOOKAHEAD


def test_engine_applies_preheat_as_temporary_target_and_freezes_integrator() -> None:
    result = ControlEngine().step(
        observation=observation(21.3),
        comfort_policy=ComfortPolicy(),
        safety_policy=SafetyPolicy(),
        state=EngineState(),
        now_utc=NOW,
        dt=timedelta(minutes=1),
        saving_level=3,
        preheat_context=context(predicted_min=20.0, authorized=True),
    )

    assert result.preheat_plan is not None
    assert result.preheat_plan.active
    assert result.requested_decision is not None
    assert result.requested_decision.state is ControlState.PREHEAT
    assert result.requested_decision.heating_request > 0.0
    assert result.comfort_result is not None
    assert result.comfort_result.integrator_frozen
    assert result.next_state.comfort.integral == 0.0
    assert ReasonCode.PREDICTED_COMFORT_RISK in result.requested_decision.reason_codes
    assert ReasonCode.PRICE_SHIFT_BENEFICIAL in result.requested_decision.reason_codes


def test_missing_preheat_context_keeps_normal_comfort_control() -> None:
    result = ControlEngine().step(
        observation=observation(20.0),
        comfort_policy=ComfortPolicy(),
        safety_policy=SafetyPolicy(),
        state=EngineState(),
        now_utc=NOW,
        dt=timedelta(minutes=1),
        saving_level=5,
        preheat_context=None,
    )

    assert result.preheat_plan is not None
    assert not result.preheat_plan.active
    assert result.preheat_plan.reason is PreheatReason.NO_PRICE_OPPORTUNITY
    assert result.requested_decision is not None
    assert result.requested_decision.state is ControlState.COMFORT
