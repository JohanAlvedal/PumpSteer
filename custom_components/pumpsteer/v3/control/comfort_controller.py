"""Deterministic comfort-only controller for PumpSteer V3.

The controller has no Home Assistant dependencies and does not consume price or
weather data. Positive comfort error and positive output both mean that more heat
is requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import ComfortPolicy, Observation, SafetyPolicy
from ..validation import aware_datetime, finite_float


@dataclass(frozen=True, slots=True)
class ComfortControllerConfig:
    """Fixed tuning and timing limits for the comfort controller.

    ``integral_gain_per_hour`` expresses heating-request degrees accumulated per
    degree of effective comfort error per hour.
    """

    proportional_gain: float = 2.4
    integral_gain_per_hour: float = 2.1
    deadband_c: float = 0.1
    maximum_heating_request: float = 15.0
    maximum_integral: float = 10.0
    maximum_dt: timedelta = timedelta(minutes=5)

    def __post_init__(self) -> None:
        for field_name in (
            "proportional_gain",
            "integral_gain_per_hour",
            "deadband_c",
            "maximum_heating_request",
            "maximum_integral",
        ):
            object.__setattr__(
                self, field_name, finite_float(getattr(self, field_name), field_name)
            )
        if self.proportional_gain < 0:
            raise ValueError("proportional_gain must be non-negative")
        if self.integral_gain_per_hour < 0:
            raise ValueError("integral_gain_per_hour must be non-negative")
        if self.deadband_c < 0:
            raise ValueError("deadband_c must be non-negative")
        if self.maximum_heating_request < 0:
            raise ValueError("maximum_heating_request must be non-negative")
        if self.maximum_integral < 0:
            raise ValueError("maximum_integral must be non-negative")
        if not isinstance(self.maximum_dt, timedelta):
            raise TypeError("maximum_dt must be a timedelta")
        if self.maximum_dt <= timedelta(0):
            raise ValueError("maximum_dt must be positive")


@dataclass(frozen=True, slots=True)
class ComfortControllerState:
    """Immutable state carried between control cycles."""

    integral: float = 0.0
    last_step_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "integral", finite_float(self.integral, "integral"))
        if self.last_step_at is not None:
            _require_utc(self.last_step_at, "last_step_at")


@dataclass(frozen=True, slots=True)
class ComfortControllerResult:
    """Explainable result of one comfort-control step."""

    heating_request: float
    comfort_error: float
    effective_error: float
    proportional_term: float
    integral_term: float
    output_saturated: bool
    integrator_frozen: bool
    dt_bounded: bool
    next_state: ComfortControllerState


class ComfortController:
    """Bounded PI controller with deadband and conditional integration."""

    def __init__(self, config: ComfortControllerConfig | None = None) -> None:
        self._config = config or ComfortControllerConfig()

    @property
    def config(self) -> ComfortControllerConfig:
        """Return immutable controller configuration."""
        return self._config

    def step(
        self,
        *,
        observation: Observation,
        policy: ComfortPolicy,
        safety_policy: SafetyPolicy,
        state: ComfortControllerState,
        now_utc: datetime,
        dt: timedelta,
        override_active: bool = False,
    ) -> ComfortControllerResult:
        """Calculate one deterministic comfort-only control step.

        Invalid or non-positive time steps are rejected. Long time steps are
        bounded before integration so a scheduler pause cannot create a large
        output change. ``override_active`` freezes the integrator while leaving
        the proportional comfort response observable.
        """
        if not isinstance(observation, Observation):
            raise TypeError("observation must be an Observation")
        if not isinstance(policy, ComfortPolicy):
            raise TypeError("policy must be a ComfortPolicy")
        if not isinstance(safety_policy, SafetyPolicy):
            raise TypeError("safety_policy must be a SafetyPolicy")
        if not isinstance(state, ComfortControllerState):
            raise TypeError("state must be a ComfortControllerState")
        now = _require_utc(now_utc, "now_utc")
        if not isinstance(dt, timedelta):
            raise TypeError("dt must be a timedelta")
        if dt <= timedelta(0):
            raise ValueError("dt must be positive")
        if observation.captured_at != now:
            raise ValueError("observation.captured_at must equal now_utc")
        if state.last_step_at is not None:
            elapsed = now - state.last_step_at
            if elapsed <= timedelta(0):
                raise ValueError("now_utc must be later than state.last_step_at")
            if abs((elapsed - dt).total_seconds()) > 1e-6:
                raise ValueError("dt must match elapsed time since last_step_at")

        bounded_dt = min(dt, self._config.maximum_dt)
        dt_bounded = bounded_dt != dt
        raw_error = observation.comfort_error(policy.target_temperature)
        effective_error = _apply_deadband(raw_error, self._config.deadband_c)
        proportional = self._config.proportional_gain * effective_error

        output_limit = min(
            self._config.maximum_heating_request,
            safety_policy.maximum_heating_request,
        )
        previous_integral = _clamp(
            state.integral,
            -self._config.maximum_integral,
            self._config.maximum_integral,
        )
        candidate_integral = previous_integral
        integrator_frozen = bool(override_active)

        if not integrator_frozen:
            dt_hours = bounded_dt.total_seconds() / 3600.0
            candidate_integral = _clamp(
                previous_integral
                + self._config.integral_gain_per_hour * effective_error * dt_hours,
                -self._config.maximum_integral,
                self._config.maximum_integral,
            )
            candidate_output = proportional + candidate_integral

            # Conditional integration accepts updates inside the actuator range,
            # or updates that drive an already saturated request back toward it.
            pushing_above = candidate_output > output_limit and effective_error > 0.0
            pushing_below = candidate_output < 0.0 and effective_error < 0.0
            if pushing_above or pushing_below:
                candidate_integral = previous_integral
                integrator_frozen = True

        raw_output = proportional + candidate_integral
        heating_request = _clamp(raw_output, 0.0, output_limit)
        output_saturated = abs(heating_request - raw_output) > 1e-12
        next_state = ComfortControllerState(
            integral=candidate_integral,
            last_step_at=now,
        )

        return ComfortControllerResult(
            heating_request=heating_request,
            comfort_error=raw_error,
            effective_error=effective_error,
            proportional_term=proportional,
            integral_term=candidate_integral,
            output_saturated=output_saturated,
            integrator_frozen=integrator_frozen,
            dt_bounded=dt_bounded,
            next_state=next_state,
        )


def _apply_deadband(error: float, deadband: float) -> float:
    """Remove the deadband while preserving continuous controller output."""
    # Temperature subtraction can place an exact decimal boundary a few ULPs
    # outside the configured band (for example 21.0 - 20.9).
    if abs(error) <= deadband + 1e-12:
        return 0.0
    if error > 0.0:
        return error - deadband
    return error + deadband


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _require_utc(value: datetime, field_name: str) -> datetime:
    result = aware_datetime(value, field_name)
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return result
