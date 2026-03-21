from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass
class PIResult:
    """Calculated controller output and diagnostics."""

    offset: float
    error: float
    derivative: float
    integral: float
    feedforward: float


class PIController:
    """Unified PI(D) controller for fake outdoor temperature offset."""

    def __init__(self) -> None:
        self.integral = 0.0
        self.last_error = 0.0
        self.last_update_time: datetime | None = None

    def reset(self, update_time: datetime) -> None:
        """Reset controller memory when operating mode requires a clean state."""
        self.integral = 0.0
        self.last_error = 0.0
        self.last_update_time = update_time

    def _compute_dt_seconds(self, update_time: datetime) -> float:
        if self.last_update_time is None:
            return 60.0
        return max((update_time - self.last_update_time).total_seconds(), 1.0)

    def compute(
        self,
        target_temp: float,
        indoor_temp: float,
        outdoor_temp: float,
        aggressiveness: float,
        update_time: datetime,
        braking_active: bool,
        kp: float,
        ki: float,
        kd: float,
        feedforward_bias: float,
        integral_clamp: float,
        output_clamp: float,
        min_fake_temp: float,
        max_fake_temp: float,
        brake_behavior: str,
        decay_per_minute_on_brake: float,
    ) -> PIResult:
        """Compute temperature offset using PI(D) with dynamic saturation limits."""
        error = target_temp - indoor_temp
        dt_seconds = self._compute_dt_seconds(update_time)
        derivative = (error - self.last_error) / dt_seconds

        integral_candidate = self.integral
        if braking_active:
            if brake_behavior == "reset":
                integral_candidate = 0.0
            elif brake_behavior == "decay":
                integral_candidate *= decay_per_minute_on_brake ** (dt_seconds / 60.0)
        else:
            integral_candidate += error * (dt_seconds / 60.0)
            integral_candidate = min(max(integral_candidate, -integral_clamp), integral_clamp)

        # Aggressiveness is handled by brake comfort windows, not PI gain scaling.
        # Keep PI gain semantics stable so comfort regulation remains predictable.
        scale = 1.0
        feedforward = feedforward_bias

        def calculate_offset(integral_value: float) -> Tuple[float, float]:
            control_signal = (kp * error) + (ki * integral_value) + (kd * derivative)
            raw_offset = -(control_signal * scale) + feedforward
            min_output_limit = -output_clamp
            max_output_limit = output_clamp
            dynamic_min_offset = min_fake_temp - outdoor_temp
            dynamic_max_offset = max_fake_temp - outdoor_temp
            min_offset = max(min_output_limit, dynamic_min_offset)
            max_offset = min(max_output_limit, dynamic_max_offset)
            limited_offset = min(max(raw_offset, min_offset), max_offset)
            return raw_offset, limited_offset

        raw_offset, limited_offset = calculate_offset(integral_candidate)

        # Freeze integration when saturated in the same direction as the control effort.
        if not braking_active and ki > 0.0 and limited_offset != raw_offset:
            at_lower_limit = limited_offset < raw_offset and error > 0.0
            at_upper_limit = limited_offset > raw_offset and error < 0.0
            if at_lower_limit or at_upper_limit:
                raw_offset, limited_offset = calculate_offset(self.integral)
            else:
                self.integral = integral_candidate
        else:
            self.integral = integral_candidate

        self.last_error = error
        self.last_update_time = update_time
        return PIResult(
            offset=limited_offset,
            error=error,
            derivative=derivative,
            integral=self.integral,
            feedforward=feedforward,
        )


class OffsetSmoother:
    """Optional first-order smoothing for controller offset."""

    def __init__(self) -> None:
        self._value = 0.0
        self._last_update_time: datetime | None = None

    def reset(self, update_time: datetime, value: float = 0.0) -> None:
        """Reset smoother state."""
        self._value = value
        self._last_update_time = update_time

    def apply(self, raw_offset: float, update_time: datetime, smoothing_minutes: float) -> float:
        """Apply exponential smoothing to offset."""
        if smoothing_minutes <= 0.0:
            self._value = raw_offset
            self._last_update_time = update_time
            return raw_offset

        if self._last_update_time is None:
            self._value = raw_offset
            self._last_update_time = update_time
            return raw_offset

        dt_seconds = max((update_time - self._last_update_time).total_seconds(), 1.0)
        tau_seconds = max(smoothing_minutes * 60.0, 1.0)
        alpha = min(max(dt_seconds / (tau_seconds + dt_seconds), 0.0), 1.0)
        self._value = self._value + (alpha * (raw_offset - self._value))
        self._last_update_time = update_time
        return self._value
