"""Deterministic output supervision and fail-safe handling."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..enums import ControlState, ReasonCode
from ..models import ControlDecision, SafetyPolicy
from ..validation import aware_datetime, finite_float


class OutputConstraint(StrEnum):
    """Constraints applied by the output supervisor."""

    HEATING_REQUEST_LIMIT = "heating_request_limit"
    CURTAILMENT_LIMIT = "curtailment_limit"
    ABSOLUTE_MINIMUM = "absolute_minimum"
    ABSOLUTE_MAXIMUM = "absolute_maximum"
    SLEW_LIMIT = "slew_limit"
    STEP_LIMIT = "step_limit"
    QUANTIZED = "quantized"
    CRITICAL_INPUT_FALLBACK = "critical_input_fallback"
    INTERNAL_FAILURE_FALLBACK = "internal_failure_fallback"


@dataclass(frozen=True, slots=True)
class SupervisorPolicy:
    """Output-device limits that complement the domain safety policy."""

    maximum_slew_per_minute: float = 1.0
    maximum_step: float = 2.0
    quantum: float = 0.5
    safe_fallback_temperature: float = 10.0

    def __post_init__(self) -> None:
        for name in (
            "maximum_slew_per_minute",
            "maximum_step",
            "quantum",
            "safe_fallback_temperature",
        ):
            object.__setattr__(self, name, finite_float(getattr(self, name), name))
        if self.maximum_slew_per_minute <= 0:
            raise ValueError("maximum_slew_per_minute must be positive")
        if self.maximum_step <= 0:
            raise ValueError("maximum_step must be positive")
        if self.quantum <= 0:
            raise ValueError("quantum must be positive")


@dataclass(frozen=True, slots=True)
class SupervisedOutput:
    """A safe output command and whether an adapter may physically apply it."""

    decision: ControlDecision
    apply_physical: bool
    constraints: tuple[OutputConstraint, ...]
    fallback_active: bool = False

    @property
    def value(self) -> float:
        """Return the final virtual outdoor temperature."""
        return self.decision.virtual_temperature


def supervise_output(
    requested: ControlDecision | None,
    *,
    safety: SafetyPolicy,
    policy: SupervisorPolicy,
    now: datetime,
    previous: SupervisedOutput | None = None,
    shadow: bool = False,
    critical_input_valid: bool = True,
    internal_failure: bool = False,
    fallback_outdoor_temperature: float | None = None,
) -> SupervisedOutput:
    """Supervise one requested output without relying on polling frequency.

    Critical failures bypass slew limiting so a previously manipulated output is
    actively replaced by passthrough or a known neutral fallback.
    """
    now = aware_datetime(now, "now")
    if internal_failure or not critical_input_valid or requested is None:
        return _safe_fallback(
            safety=safety,
            policy=policy,
            now=now,
            shadow=shadow,
            internal_failure=internal_failure or requested is None,
            fallback_outdoor_temperature=fallback_outdoor_temperature,
        )

    heating = min(requested.heating_request, safety.maximum_heating_request)
    curtailment = min(requested.curtailment, safety.maximum_curtailment)
    constraints: list[OutputConstraint] = []
    reasons = list(requested.reason_codes)

    if heating != requested.heating_request:
        constraints.append(OutputConstraint.HEATING_REQUEST_LIMIT)
    if curtailment != requested.curtailment:
        constraints.append(OutputConstraint.CURTAILMENT_LIMIT)

    target = requested.outdoor_temperature - heating + curtailment
    bounded = _clamp_absolute(target, safety, constraints)

    if previous is not None:
        elapsed = (now - previous.decision.decided_at).total_seconds()
        if elapsed < 0:
            raise ValueError("now cannot be earlier than the previous output")
        slew_delta = policy.maximum_slew_per_minute * elapsed / 60.0
        allowed_delta = min(policy.maximum_step, slew_delta)
        delta = bounded - previous.value
        if abs(delta) > allowed_delta:
            bounded = previous.value + _sign(delta) * allowed_delta
            if slew_delta <= policy.maximum_step:
                constraints.append(OutputConstraint.SLEW_LIMIT)
            else:
                constraints.append(OutputConstraint.STEP_LIMIT)

    final_value = _quantize_within_bounds(
        bounded,
        policy.quantum,
        safety,
        previous_value=previous.value if previous is not None else None,
    )
    if abs(final_value - bounded) > 1e-12:
        constraints.append(OutputConstraint.QUANTIZED)

    if any(
        constraint
        in {
            OutputConstraint.HEATING_REQUEST_LIMIT,
            OutputConstraint.CURTAILMENT_LIMIT,
            OutputConstraint.ABSOLUTE_MINIMUM,
            OutputConstraint.ABSOLUTE_MAXIMUM,
        }
        for constraint in constraints
    ):
        _append_reason(reasons, ReasonCode.OUTPUT_SATURATED)
    if (
        OutputConstraint.SLEW_LIMIT in constraints
        or OutputConstraint.STEP_LIMIT in constraints
    ):
        _append_reason(reasons, ReasonCode.OUTPUT_RATE_LIMITED)
    if shadow:
        _append_reason(reasons, ReasonCode.SHADOW_MODE)

    decision = _decision_for_value(
        requested=requested,
        decided_at=now,
        value=final_value,
        reasons=reasons,
    )
    return SupervisedOutput(
        decision=decision,
        apply_physical=not shadow,
        constraints=tuple(constraints),
    )


def _safe_fallback(
    *,
    safety: SafetyPolicy,
    policy: SupervisorPolicy,
    now: datetime,
    shadow: bool,
    internal_failure: bool,
    fallback_outdoor_temperature: float | None,
) -> SupervisedOutput:
    constraints = [
        OutputConstraint.INTERNAL_FAILURE_FALLBACK
        if internal_failure
        else OutputConstraint.CRITICAL_INPUT_FALLBACK
    ]
    reason = (
        ReasonCode.INTERNAL_FAILSAFE
        if internal_failure
        else ReasonCode.CRITICAL_SENSOR_INVALID
    )
    if fallback_outdoor_temperature is None:
        outdoor = policy.safe_fallback_temperature
    else:
        try:
            outdoor = finite_float(
                fallback_outdoor_temperature, "fallback_outdoor_temperature"
            )
        except (TypeError, ValueError):
            outdoor = policy.safe_fallback_temperature
            constraints[0] = OutputConstraint.INTERNAL_FAILURE_FALLBACK
            reason = ReasonCode.INTERNAL_FAILSAFE

    bounded = _clamp_absolute(outdoor, safety, constraints)
    final_value = _quantize_within_bounds(bounded, policy.quantum, safety)
    if abs(final_value - bounded) > 1e-12:
        constraints.append(OutputConstraint.QUANTIZED)
    reasons = [reason]
    if (
        OutputConstraint.ABSOLUTE_MINIMUM in constraints
        or OutputConstraint.ABSOLUTE_MAXIMUM in constraints
    ):
        reasons.append(ReasonCode.OUTPUT_SATURATED)
    if shadow:
        reasons.append(ReasonCode.SHADOW_MODE)
    decision = ControlDecision.create(
        decided_at=now,
        state=ControlState.FAILSAFE,
        outdoor_temperature=final_value,
        reason_codes=reasons,
    )
    return SupervisedOutput(
        decision=decision,
        apply_physical=not shadow,
        constraints=tuple(constraints),
        fallback_active=True,
    )


def _clamp_absolute(
    value: float,
    safety: SafetyPolicy,
    constraints: list[OutputConstraint],
) -> float:
    if value < safety.minimum_virtual_temperature:
        constraints.append(OutputConstraint.ABSOLUTE_MINIMUM)
        return safety.minimum_virtual_temperature
    if value > safety.maximum_virtual_temperature:
        constraints.append(OutputConstraint.ABSOLUTE_MAXIMUM)
        return safety.maximum_virtual_temperature
    return value


def _quantize_within_bounds(
    value: float,
    quantum: float,
    safety: SafetyPolicy,
    *,
    previous_value: float | None = None,
) -> float:
    scaled = value / quantum
    if previous_value is not None and value > previous_value:
        quantized = math.floor(scaled) * quantum
    elif previous_value is not None and value < previous_value:
        quantized = math.ceil(scaled) * quantum
    else:
        quantized = round(scaled) * quantum
    return max(
        safety.minimum_virtual_temperature,
        min(safety.maximum_virtual_temperature, quantized),
    )


def _decision_for_value(
    *,
    requested: ControlDecision,
    decided_at: datetime,
    value: float,
    reasons: list[ReasonCode],
) -> ControlDecision:
    delta = value - requested.outdoor_temperature
    heating = max(0.0, -delta)
    curtailment = max(0.0, delta)
    return ControlDecision.create(
        decided_at=decided_at,
        state=requested.state,
        outdoor_temperature=requested.outdoor_temperature,
        heating_request=heating,
        curtailment=curtailment,
        reason_codes=reasons,
    )


def _append_reason(reasons: list[ReasonCode], reason: ReasonCode) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _sign(value: float) -> float:
    return 1.0 if value >= 0 else -1.0
