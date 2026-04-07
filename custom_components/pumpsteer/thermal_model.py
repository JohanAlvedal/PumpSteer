# thermal_model.py

"""
Empirical thermal model for PumpSteer.

Estimates the house cooling rate constant k (°C/h per °C temperature delta)
from samples collected during braking periods — the only time we know for
certain that the heat pump is not delivering heat.

The model answers:
  "Given outdoor_temp and brake duration, how much will indoor_temp drop?"

Used by sensor.py to:
  - Decide if the house can survive an upcoming brake within the comfort floor
  - Expose predicted drop as a sensor attribute for dashboard visibility
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Optional

_LOGGER = logging.getLogger(__name__)

# Minimum braking samples before the model is considered valid.
_MIN_SAMPLES = 20

# Fallback k if insufficient braking history exists.
# 0.05 °C/h per °C delta → house at 21°C inside, -4°C outside (delta=25°C)
# cools at ~1.25°C/h — conservative but plausible for a Swedish wood-frame house.
_FALLBACK_K = 0.05

# Physically plausible range for k.
# < 0.005: essentially no heat loss (unrealistic)
# > 0.5:   loses 12.5°C/h at delta=25°C (way too leaky)
_K_MIN = 0.005
_K_MAX = 0.5

# Ring buffer size for indoor temperature samples used to compute delta_indoor_dt.
# 10 samples × ~60s polling = ~10 minute window.
_TEMP_BUFFER_SIZE = 10


@dataclass
class ThermalSample:
    """One data point collected during a braking period."""
    indoor_temp: float       # °C at sample time
    outdoor_temp: float      # °C at sample time
    rate: float              # °C/h, negative when cooling


class ThermalModel:
    """
    Estimates house cooling rate from braking-period samples.

    Cooling model:
        dT_indoor/dt = -k * (indoor - outdoor)

    k is estimated by linear regression over samples collected
    exclusively during braking mode, where we know the heat pump
    is not delivering heat.

    Persistence: k is stored as a sensor attribute and restored
    via RestoreEntity on HA restart — no Recorder dependency.
    """

    def __init__(self) -> None:
        self._k: float = _FALLBACK_K
        self._valid: bool = False
        self._sample_count: int = 0

        # Braking samples accumulated this session.
        self._samples: list[ThermalSample] = []

        # Ring buffer of (timestamp, indoor_temp) for rate computation.
        self._temp_history: Deque[tuple[datetime, float]] = deque(
            maxlen=_TEMP_BUFFER_SIZE
        )

    # ── Public properties ──────────────────────────────────────────────────────

    @property
    def k(self) -> float:
        """Cooling rate constant. °C/h per °C (indoor - outdoor)."""
        return self._k

    @property
    def is_valid(self) -> bool:
        """True if k was fitted from real data (not fallback)."""
        return self._valid

    @property
    def sample_count(self) -> int:
        return self._sample_count

    # ── Persistence (called by sensor.py RestoreEntity) ───────────────────────

    def restore_k(self, k: float) -> None:
        """
        Restore k from a previously saved sensor attribute.
        Called once at HA startup before the first update cycle.
        """
        if _K_MIN < k < _K_MAX:
            self._k = k
            self._valid = True
            _LOGGER.debug("ThermalModel: restored k=%.4f from state", k)
        else:
            _LOGGER.debug(
                "ThermalModel: restored k=%.4f is out of range, using fallback", k
            )

    # ── Sample collection ──────────────────────────────────────────────────────

    def record_temp(self, now: datetime, indoor_temp: float) -> None:
        """
        Called every polling cycle regardless of mode.
        Maintains the ring buffer used to compute cooling rate.
        """
        self._temp_history.append((now, indoor_temp))

    def collect_braking_sample(
        self,
        indoor_temp: float,
        outdoor_temp: float,
    ) -> None:
        """
        Called each polling cycle while mode == braking.
        Computes the current cooling rate from the ring buffer
        and stores it as a sample for regression.

        Skips the sample if the buffer is too short or the
        temperature delta is too small to be meaningful.
        """
        rate = self._compute_rate()
        if rate is None:
            return

        delta_T = indoor_temp - outdoor_temp
        if abs(delta_T) < 2.0:
            # Too small a delta — measurement noise dominates.
            return

        self._samples.append(
            ThermalSample(
                indoor_temp=indoor_temp,
                outdoor_temp=outdoor_temp,
                rate=rate,
            )
        )

    def _compute_rate(self) -> Optional[float]:
        """
        Compute indoor cooling rate (°C/h) from the ring buffer.
        Returns None if the buffer holds fewer than 2 entries
        or the time span is too short.
        """
        if len(self._temp_history) < 2:
            return None

        t_old, temp_old = self._temp_history[0]
        t_now, temp_now = self._temp_history[-1]

        dt_hours = (t_now - t_old).total_seconds() / 3600.0
        if dt_hours < (1 / 60):  # less than 1 minute — skip
            return None

        return (temp_now - temp_old) / dt_hours

    # ── Model fitting ──────────────────────────────────────────────────────────

    def fit(self) -> None:
        """
        Fit k from accumulated braking samples.
        Called once per day (e.g. at midnight alongside price threshold refresh).

        Uses ordinary least squares:
            rate = -k * delta_T
            k = -sum(rate * delta_T) / sum(delta_T²)
        """
        if len(self._samples) < _MIN_SAMPLES:
            _LOGGER.debug(
                "ThermalModel: only %d braking samples, keeping k=%.4f",
                len(self._samples),
                self._k,
            )
            return

        sum_xy = 0.0
        sum_xx = 0.0
        for s in self._samples:
            delta_T = s.indoor_temp - s.outdoor_temp
            sum_xy += s.rate * delta_T
            sum_xx += delta_T ** 2

        if sum_xx < 1e-6:
            _LOGGER.debug("ThermalModel: degenerate data, skipping fit")
            return

        k = -sum_xy / sum_xx

        if _K_MIN < k < _K_MAX:
            self._k = k
            self._valid = True
            self._sample_count = len(self._samples)
            _LOGGER.debug(
                "ThermalModel: fitted k=%.4f from %d samples",
                k,
                self._sample_count,
            )
        else:
            _LOGGER.warning(
                "ThermalModel: fitted k=%.4f outside [%.3f, %.3f], keeping k=%.4f",
                k, _K_MIN, _K_MAX, self._k,
            )

        # Clear samples after fit — next day starts fresh.
        self._samples.clear()

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict_drop(
        self,
        indoor: float,
        outdoor: float,
        duration_minutes: float,
    ) -> float:
        """
        Predict indoor temperature drop over duration_minutes
        with no heating active.

        Returns degrees of drop (positive number).
        """
        delta_T = max(0.0, indoor - outdoor)
        return self._k * delta_T * (duration_minutes / 60.0)

    def brake_is_safe(
        self,
        indoor: float,
        outdoor: float,
        brake_duration_minutes: float,
        comfort_floor: float,
    ) -> bool:
        """
        True if indoor temp stays above comfort_floor
        for the full brake duration.
        """
        drop = self.predict_drop(indoor, outdoor, brake_duration_minutes)
        predicted = indoor - drop
        safe = predicted >= comfort_floor
        _LOGGER.debug(
            "ThermalModel: safe=%s drop=%.2f°C end=%.2f°C floor=%.2f°C k=%.4f",
            safe, drop, predicted, comfort_floor, self._k,
        )
        return safe
