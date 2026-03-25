"""
PumpSteer control module.

Contains:
  - PIResult / PIController  — discrete-time PI controller used by sensor.py

Note: PumpSteerConfigFlow lives in config_flow.py (the standard HA location).
The duplicate class that was previously in this file has been removed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

_LOGGER = logging.getLogger(__name__)


# ── PI Controller ─────────────────────────────────────────────────────────────


@dataclass
class PIResult:
    """Result from one PI controller compute step."""

    offset: float
    p_term: float
    i_term: float
    error: float


class PIController:
    """
    Discrete-time PI controller for PumpSteer.
    offset < 0 → heat more (sensor.py negates to get positive demand).
    Anti-windup via integral clamp.
    brake_behavior='freeze' keeps integral constant while braking.
    brake_behavior='decay' slowly reduces it.
    """

    def __init__(self) -> None:
        self._integral: float = 0.0
        self._last_time: Optional[datetime] = None
        self._last_error: float = 0.0

    def reset(self, now: datetime) -> None:
        """Reset controller state (on mode switch or safe mode entry)."""
        self._integral = 0.0
        self._last_time = now
        self._last_error = 0.0
        _LOGGER.debug("PIController reset")

    def compute(
        self,
        target_temp: float,
        indoor_temp: float,
        outdoor_temp: float,
        aggressiveness: float,
        update_time: datetime,
        braking_active: bool = False,
        kp: float = 8.0,
        ki: float = 0.05,
        kd: float = 0.0,
        feedforward_bias: float = 0.0,
        integral_clamp: float = 10.0,
        output_clamp: float = 20.0,
        min_fake_temp: float = -25.0,
        max_fake_temp: float = 25.0,
        brake_behavior: str = "freeze",
        decay_per_minute_on_brake: float = 0.98,
    ) -> PIResult:
        if self._last_time is None:
            dt_minutes = 1.0
        else:
            dt_seconds = (update_time - self._last_time).total_seconds()
            dt_minutes = max(dt_seconds / 60.0, 0.01)
        self._last_time = update_time

        error = target_temp - indoor_temp
        p_term = kp * error

        if braking_active:
            if brake_behavior == "decay":
                self._integral *= decay_per_minute_on_brake**dt_minutes
        else:
            self._integral += ki * error * dt_minutes
            self._integral = max(-integral_clamp, min(integral_clamp, self._integral))
        i_term = self._integral

        d_term = 0.0
        if kd > 0 and dt_minutes > 0:
            d_term = kd * (error - self._last_error) / dt_minutes
        self._last_error = error

        raw_output = -(p_term + i_term + d_term + feedforward_bias)
        clamped = max(-output_clamp, min(output_clamp, raw_output))

        _LOGGER.debug(
            "PI: error=%.2f P=%.2f I=%.2f → offset=%.2f (dt=%.1f min, braking=%s)",
            error,
            p_term,
            i_term,
            clamped,
            dt_minutes,
            braking_active,
        )
        return PIResult(offset=clamped, p_term=p_term, i_term=i_term, error=error)
