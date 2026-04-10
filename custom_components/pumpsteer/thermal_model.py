# thermal_model.py

"""
Empirical thermal model for PumpSteer.

This module estimates the house cooling rate constant k
(°C/h per °C temperature delta) from samples collected during
braking periods, when reduced heating demand makes thermal loss
easier to observe.

In PumpSteer 2.1.0, this model is used for:
- observability
- telemetry
- future validation work

It does NOT directly control brake/pre-brake/preheat decisions in 2.1.0.

The model can estimate expected indoor temperature drop during
reduced-heating periods, but these prediction helpers are currently
diagnostic/future-facing and not part of the active control path.
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
# 0.05 °C/h per °C delta means a house at 21°C inside and -4°C outside
# (delta = 25°C) cools at about 1.25°C/h. This is conservative but plausible
# for a Swedish wood-frame house.
_FALLBACK_K = 0.05

# Physically plausible range for k.
# < 0.005: unrealistically low heat loss
# > 0.5: unrealistically high heat loss
_K_MIN = 0.005
_K_MAX = 0.5

# Ring buffer size for indoor temperature samples used to compute dT/dt.
# 10 samples × ~60 s polling gives roughly a 10 minute window.
_TEMP_BUFFER_SIZE = 10

# Minimum history span before rate is considered reliable.
# A few minutes gives a more stable estimate than a near-instant sample.
_MIN_RATE_WINDOW_MINUTES = 3.0

# Plausible bounds for measured indoor temperature rate (°C/h).
# These are intentionally conservative and only reject obvious spikes/noise.
_MIN_RATE_C_PER_HOUR = -5.0
_MAX_RATE_C_PER_HOUR = 1.0


@dataclass
class ThermalSample:
    """One data point collected during a braking period."""

    indoor_temp: float
    outdoor_temp: float
    rate: float  # °C/h, negative when indoor temperature is falling


class ThermalModel:
    """
    Estimate house cooling rate from braking-period samples.

    Simplified cooling model:
        dT_indoor/dt = -k * (indoor - outdoor)

    k is estimated by linear regression over samples collected
    during braking periods.

    In PumpSteer 2.1.0, this model is observational only:
    - it may expose fitted values and sample counts
    - it may support diagnostics and future validation
    - it does NOT directly drive the state machine

    Persistence:
    k can be restored from saved sensor state so the model survives
    Home Assistant restarts without depending on Recorder-based history.
    """

    def __init__(self) -> None:
        self._k: float = _FALLBACK_K
        self._valid: bool = False
        self._sample_count: int = 0

        # Braking samples accumulated since the last fit cycle.
        self._samples: list[ThermalSample] = []

        # Ring buffer of (timestamp, indoor_temp) used to estimate cooling rate.
        self._temp_history: Deque[tuple[datetime, float]] = deque(
            maxlen=_TEMP_BUFFER_SIZE
        )

    # ── Public properties ──────────────────────────────────────────────────────

    @property
    def k(self) -> float:
        """Estimated cooling rate constant in °C/h per °C delta."""
        return self._k

    @property
    def is_valid(self) -> bool:
        """True if k was fitted from collected data instead of fallback."""
        return self._valid

    @property
    def sample_count(self) -> int:
        """Number of samples used in the most recent successful fit."""
        return self._sample_count

    @property
    def pending_samples(self) -> int:
        """Number of collected samples waiting for the next fit."""
        return len(self._samples)

    # ── Persistence ────────────────────────────────────────────────────────────

    def restore_k(self, k: float) -> None:
        """
        Restore k from previously saved state.

        Intended to be called once during startup before the first
        update cycle.
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
        Record indoor temperature for later cooling-rate estimation.

        This should be called every polling cycle when indoor temperature
        is available.
        """
        self._temp_history.append((now, indoor_temp))

    def collect_braking_sample(
        self,
        indoor_temp: float,
        outdoor_temp: float,
    ) -> None:
        """
        Collect one sample during braking periods.

        Uses the recent indoor temperature history to estimate current
        cooling rate and stores the result for later fitting.

        Samples are skipped when:
        - the history window is too short
        - the indoor/outdoor temperature delta is too small to be meaningful
        - the measured rate does not indicate actual cooling
        - the measured rate is clearly implausible
        """
        rate = self._compute_rate()
        if rate is None:
            return

        # Only use real cooling samples.
        # If indoor temperature is still flat/rising, the sample is not useful
        # for estimating passive heat loss during braking.
        if rate >= 0.0:
            return

        # Reject obvious spikes/noise before they contaminate the fit.
        if rate < _MIN_RATE_C_PER_HOUR or rate > _MAX_RATE_C_PER_HOUR:
            return

        delta_t = indoor_temp - outdoor_temp
        if abs(delta_t) < 2.0:
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
        Compute indoor temperature rate of change in °C/h.

        Returns None if:
        - there are fewer than two samples
        - the history span is too short to be reliable
        """
        if len(self._temp_history) < 2:
            return None

        t_old, temp_old = self._temp_history[0]
        t_now, temp_now = self._temp_history[-1]

        dt_hours = (t_now - t_old).total_seconds() / 3600.0
        if dt_hours < (_MIN_RATE_WINDOW_MINUTES / 60.0):
            # Too little history — the estimate becomes noisy and unstable.
            return None

        return (temp_now - temp_old) / dt_hours

    # ── Model fitting ──────────────────────────────────────────────────────────

    def fit(self) -> None:
        """
        Fit k from accumulated braking samples.

        Uses ordinary least squares on the simplified model:
            rate = -k * delta_T
            k = -sum(rate * delta_T) / sum(delta_T²)

        In PumpSteer 2.1.0, fitting improves diagnostics and observability.
        It does not by itself activate any control behavior.
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
        for sample in self._samples:
            delta_t = sample.indoor_temp - sample.outdoor_temp
            sum_xy += sample.rate * delta_t
            sum_xx += delta_t**2

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
                k,
                _K_MIN,
                _K_MAX,
                self._k,
            )

        # Clear samples after fit so a new learning window can begin.
        self._samples.clear()

    # ── Prediction helpers (diagnostic / future-facing) ───────────────────────

    def predict_drop(
        self,
        indoor: float,
        outdoor: float,
        duration_minutes: float,
    ) -> float:
        """
        Estimate indoor temperature drop over a reduced-heating period.

        Returns the predicted drop in degrees Celsius as a positive number.

        In PumpSteer 2.1.0, this is a diagnostic/future-facing helper and is
        not part of the active state-machine decision path.
        """
        delta_t = max(0.0, indoor - outdoor)
        return self._k * delta_t * (duration_minutes / 60.0)

    def brake_is_safe(
        self,
        indoor: float,
        outdoor: float,
        brake_duration_minutes: float,
        comfort_floor: float,
    ) -> bool:
        """
        Estimate whether indoor temperature would remain above comfort_floor.

        This helper uses predict_drop() and returns True when the predicted
        end temperature remains at or above the comfort floor.

        In PumpSteer 2.1.0, this is diagnostic/future-facing only and does
        not directly gate brake/pre-brake decisions.
        """
        drop = self.predict_drop(indoor, outdoor, brake_duration_minutes)
        predicted = indoor - drop
        safe = predicted >= comfort_floor
        _LOGGER.debug(
            "ThermalModel: safe=%s drop=%.2f°C end=%.2f°C floor=%.2f°C k=%.4f",
            safe,
            drop,
            predicted,
            comfort_floor,
            self._k,
        )
        return safe
