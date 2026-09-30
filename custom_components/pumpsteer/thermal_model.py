# thermal_model.py

"""
Empirical thermal model for PumpSteer.

The model estimates the house's observed cooling response during PumpSteer braking.
It deliberately learns only from relevant heating/braking periods; it is not intended
to accumulate general year-round household telemetry.

In PumpSteer 2.2.x the fitted model remains diagnostic with respect to control
decisions. It can predict expected temperature drop and validate those predictions,
but it does NOT directly change brake depth or state-machine decisions.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Optional, Sequence

_LOGGER = logging.getLogger(__name__)

# Minimum braking samples before the model is considered valid.
_MIN_SAMPLES = 20

# Keep learning memory bounded even if several short sessions occur before a fit.
# At approximately one sample/minute this is at most about four hours of relevant data.
_MAX_LEARNING_SAMPLES = 240

# Fallback k if insufficient braking history exists.
_FALLBACK_K = 0.05

# Physically plausible range for k.
_K_MIN = 0.005
_K_MAX = 0.5

# Small rolling buffer used only to estimate dT/dt. This is not retained training data.
_TEMP_BUFFER_SIZE = 10

# Minimum history span before rate is considered reliable.
_MIN_RATE_WINDOW_MINUTES = 3.0

# Plausible bounds for measured indoor temperature rate (°C/h).
_MIN_RATE_C_PER_HOUR = -5.0
_MAX_RATE_C_PER_HOUR = 1.0

# Validation sessions shorter than this are too sensitive to sensor noise.
_MIN_VALIDATION_SESSION_MINUTES = 10.0


@dataclass
class ThermalSample:
    """One relevant data point collected during a stable braking period."""

    indoor_temp: float
    outdoor_temp: float
    rate: float  # °C/h, negative when indoor temperature is falling


@dataclass
class _ValidationSession:
    """Small in-memory summary used to validate one relevant brake session."""

    start_time: datetime
    start_indoor: float
    prediction_k: float
    prediction_valid: bool
    outdoor_sum: float
    outdoor_samples: int


class ThermalModel:
    """Estimate and validate observed house cooling response during braking."""

    def __init__(self) -> None:
        self._k: float = _FALLBACK_K
        self._valid: bool = False
        self._sample_count: int = 0
        self._fit_rmse: Optional[float] = None

        # Only relevant braking samples are retained, and the buffer is bounded.
        self._samples: Deque[ThermalSample] = deque(maxlen=_MAX_LEARNING_SAMPLES)

        # Tiny rolling buffer used to estimate indoor temperature rate.
        self._temp_history: Deque[tuple[datetime, float]] = deque(
            maxlen=_TEMP_BUFFER_SIZE
        )

        # Session-level validation statistics. Raw sessions are never persisted.
        self._session: Optional[_ValidationSession] = None
        self._learning_sessions: int = 0
        self._validated_sessions: int = 0
        self._prediction_mae: Optional[float] = None
        self._last_prediction_error: Optional[float] = None
        self._last_session_duration_minutes: Optional[float] = None
        self._last_session_actual_drop: Optional[float] = None
        self._last_session_predicted_drop: Optional[float] = None

    # ── Public properties ──────────────────────────────────────────────────────

    @property
    def k(self) -> float:
        """Estimated cooling rate constant in °C/h per °C delta."""
        return self._k

    @property
    def is_valid(self) -> bool:
        """True if k was fitted from relevant braking data."""
        return self._valid

    @property
    def sample_count(self) -> int:
        """Number of samples used in the most recent successful fit."""
        return self._sample_count

    @property
    def pending_samples(self) -> int:
        """Number of relevant samples waiting for the next fit."""
        return len(self._samples)

    @property
    def fit_rmse(self) -> Optional[float]:
        """RMSE of the most recent successful dT/dt fit in °C/h."""
        return self._fit_rmse

    @property
    def learning_sessions(self) -> int:
        """Number of completed relevant thermal-learning sessions."""
        return self._learning_sessions

    @property
    def validated_sessions(self) -> int:
        """Number of sessions validated using an already fitted model."""
        return self._validated_sessions

    @property
    def prediction_mae(self) -> Optional[float]:
        """Running mean absolute prediction error across validated sessions."""
        return self._prediction_mae

    @property
    def last_prediction_error(self) -> Optional[float]:
        """Signed error from the latest validated session: actual - predicted drop."""
        return self._last_prediction_error

    @property
    def last_session_duration_minutes(self) -> Optional[float]:
        return self._last_session_duration_minutes

    @property
    def last_session_actual_drop(self) -> Optional[float]:
        return self._last_session_actual_drop

    @property
    def last_session_predicted_drop(self) -> Optional[float]:
        return self._last_session_predicted_drop

    @property
    def validation_session_active(self) -> bool:
        return self._session is not None

    @property
    def confidence(self) -> float:
        """Return a conservative 0..1 diagnostic confidence score.

        This is intentionally a heuristic quality indicator, not a statistical
        probability. It combines fit sample count, fit residual quality, completed
        learning sessions and real prediction validation.
        """
        if not self._valid:
            return 0.0

        sample_score = min(1.0, self._sample_count / 60.0)
        fit_score = (
            0.5
            if self._fit_rmse is None
            else max(0.0, min(1.0, 1.0 - (self._fit_rmse / 1.0)))
        )
        session_score = min(1.0, self._learning_sessions / 5.0)
        validation_score = (
            0.5
            if self._prediction_mae is None
            else max(0.0, min(1.0, 1.0 - (self._prediction_mae / 1.0)))
        )

        return max(
            0.0,
            min(
                1.0,
                0.35 * sample_score
                + 0.35 * fit_score
                + 0.15 * session_score
                + 0.15 * validation_score,
            ),
        )

    # ── Persistence ────────────────────────────────────────────────────────────

    def restore_k(self, k: float) -> None:
        """Restore k from previously saved Home Assistant state."""
        if _K_MIN < k < _K_MAX:
            self._k = k
            self._valid = True
            _LOGGER.debug("ThermalModel: restored k=%.4f from state", k)
        else:
            _LOGGER.debug(
                "ThermalModel: restored k=%.4f is out of range, using fallback", k
            )

    def restore_diagnostics(
        self,
        *,
        sample_count: int = 0,
        fit_rmse: Optional[float] = None,
        learning_sessions: int = 0,
        validated_sessions: int = 0,
        prediction_mae: Optional[float] = None,
    ) -> None:
        """Restore compact model-quality summaries without restoring raw samples."""
        self._sample_count = max(0, int(sample_count))
        self._fit_rmse = self._finite_or_none(fit_rmse)
        self._learning_sessions = max(0, int(learning_sessions))
        self._validated_sessions = max(0, int(validated_sessions))
        self._prediction_mae = self._finite_or_none(prediction_mae)

    @staticmethod
    def _finite_or_none(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) and numeric >= 0.0 else None

    # ── Temperature history and learning samples ───────────────────────────────

    def record_temp(self, now: datetime, indoor_temp: float) -> None:
        """Record one value in the fixed-size dT/dt history buffer."""
        self._temp_history.append((now, indoor_temp))

    def reset_temp_history(self, now: datetime, indoor_temp: float) -> None:
        """Start a fresh rate window when stable thermal learning becomes eligible."""
        self._temp_history.clear()
        self._temp_history.append((now, indoor_temp))

    def collect_braking_sample(
        self,
        indoor_temp: float,
        outdoor_temp: float,
    ) -> bool:
        """Collect one relevant stable-braking sample.

        The caller is responsible for deciding whether current operating conditions
        are relevant for learning. This method still rejects noisy/non-cooling data.

        Returns True when a sample was accepted.
        """
        rate = self._compute_rate()
        if rate is None:
            return False

        if rate >= 0.0:
            return False

        if rate < _MIN_RATE_C_PER_HOUR or rate > _MAX_RATE_C_PER_HOUR:
            return False

        delta_t = indoor_temp - outdoor_temp
        if abs(delta_t) < 2.0:
            return False

        self._samples.append(
            ThermalSample(
                indoor_temp=indoor_temp,
                outdoor_temp=outdoor_temp,
                rate=rate,
            )
        )
        return True

    def _compute_rate(self) -> Optional[float]:
        """Compute indoor temperature rate of change in °C/h."""
        if len(self._temp_history) < 2:
            return None

        t_old, temp_old = self._temp_history[0]
        t_now, temp_now = self._temp_history[-1]

        dt_hours = (t_now - t_old).total_seconds() / 3600.0
        if dt_hours < (_MIN_RATE_WINDOW_MINUTES / 60.0):
            return None

        return (temp_now - temp_old) / dt_hours

    # ── Model fitting ──────────────────────────────────────────────────────────

    def fit(self) -> bool:
        """Fit k from accumulated relevant braking samples.

        Returns True when a new valid fit was accepted.
        """
        if len(self._samples) < _MIN_SAMPLES:
            _LOGGER.debug(
                "ThermalModel: only %d relevant braking samples, keeping k=%.4f",
                len(self._samples),
                self._k,
            )
            return False

        samples = list(self._samples)
        sum_xy = 0.0
        sum_xx = 0.0
        for sample in samples:
            delta_t = sample.indoor_temp - sample.outdoor_temp
            sum_xy += sample.rate * delta_t
            sum_xx += delta_t**2

        if sum_xx < 1e-6:
            _LOGGER.debug("ThermalModel: degenerate data, skipping fit")
            return False

        k = -sum_xy / sum_xx

        if _K_MIN < k < _K_MAX:
            residual_sq = 0.0
            for sample in samples:
                delta_t = sample.indoor_temp - sample.outdoor_temp
                predicted_rate = -k * delta_t
                residual_sq += (sample.rate - predicted_rate) ** 2

            self._k = k
            self._valid = True
            self._sample_count = len(samples)
            self._fit_rmse = math.sqrt(residual_sq / len(samples))
            _LOGGER.info(
                "ThermalModel: fitted k=%.4f from %d relevant samples (RMSE=%.3f°C/h)",
                k,
                self._sample_count,
                self._fit_rmse,
            )
            self._samples.clear()
            return True

        _LOGGER.warning(
            "ThermalModel: fitted k=%.4f outside [%.3f, %.3f], keeping k=%.4f",
            k,
            _K_MIN,
            _K_MAX,
            self._k,
        )
        self._samples.clear()
        return False

    # ── Session validation ─────────────────────────────────────────────────────

    def start_validation_session(
        self,
        now: datetime,
        indoor_temp: float,
        outdoor_temp: float,
    ) -> None:
        """Start one relevant stable-braking validation session."""
        if self._session is not None:
            return

        self._session = _ValidationSession(
            start_time=now,
            start_indoor=indoor_temp,
            prediction_k=self._k,
            prediction_valid=self._valid,
            outdoor_sum=outdoor_temp,
            outdoor_samples=1,
        )

    def update_validation_session(self, outdoor_temp: float) -> None:
        """Update the compact outdoor-temperature summary for an active session."""
        if self._session is None:
            return
        self._session.outdoor_sum += outdoor_temp
        self._session.outdoor_samples += 1

    def end_validation_session(self, now: datetime, indoor_temp: float) -> bool:
        """Finish a session and compare predicted with actual temperature drop.

        Returns True when the session was long enough to count as a learning session.
        Validation error statistics are updated only if the model was already fitted
        when the session started.
        """
        session = self._session
        self._session = None
        if session is None:
            return False

        duration_minutes = (now - session.start_time).total_seconds() / 60.0
        if duration_minutes < _MIN_VALIDATION_SESSION_MINUTES:
            return False

        actual_drop = max(0.0, session.start_indoor - indoor_temp)
        avg_outdoor = session.outdoor_sum / max(session.outdoor_samples, 1)
        predicted_drop = self._predict_drop_with_k(
            session.prediction_k,
            session.start_indoor,
            avg_outdoor,
            duration_minutes,
        )

        self._learning_sessions += 1
        self._last_session_duration_minutes = duration_minutes
        self._last_session_actual_drop = actual_drop
        self._last_session_predicted_drop = predicted_drop

        if session.prediction_valid:
            error = actual_drop - predicted_drop
            abs_error = abs(error)
            previous_count = self._validated_sessions
            previous_total = (self._prediction_mae or 0.0) * previous_count
            self._validated_sessions += 1
            self._prediction_mae = (
                previous_total + abs_error
            ) / self._validated_sessions
            self._last_prediction_error = error
            _LOGGER.info(
                "ThermalModel validation: duration=%.0fmin actual_drop=%.2f°C "
                "predicted_drop=%.2f°C error=%+.2f°C",
                duration_minutes,
                actual_drop,
                predicted_drop,
                error,
            )

        return True

    def cancel_validation_session(self) -> None:
        """Discard an active validation session without changing statistics."""
        self._session = None

    # ── Prediction helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _predict_drop_with_k(
        k: float,
        indoor: float,
        outdoor: float,
        duration_minutes: float,
    ) -> float:
        delta_t = max(0.0, indoor - outdoor)
        return max(0.0, k * delta_t * (duration_minutes / 60.0))

    def predict_drop(
        self,
        indoor: float,
        outdoor: float,
        duration_minutes: float,
    ) -> float:
        """Estimate indoor temperature drop for a constant outdoor temperature."""
        return self._predict_drop_with_k(
            self._k,
            indoor,
            outdoor,
            duration_minutes,
        )

    def predict_drop_profile(
        self,
        indoor: float,
        current_outdoor: float,
        future_outdoor_temps: Optional[Sequence[float]],
        duration_minutes: float,
        step_minutes: float = 60.0,
    ) -> float:
        """Estimate temperature drop using the available future outdoor profile.

        The model advances in bounded steps. When the requested duration extends past
        the available forecast, the last available outdoor temperature is held.
        """
        if duration_minutes <= 0.0:
            return 0.0

        profile = [current_outdoor]
        if future_outdoor_temps:
            profile.extend(float(value) for value in future_outdoor_temps)

        temp = indoor
        remaining = duration_minutes
        index = 0
        step_minutes = max(1.0, step_minutes)

        while remaining > 0.0:
            dt_minutes = min(step_minutes, remaining)
            outdoor = profile[min(index, len(profile) - 1)]
            delta_t = max(0.0, temp - outdoor)
            temp -= self._k * delta_t * (dt_minutes / 60.0)
            remaining -= dt_minutes
            index += 1

        return max(0.0, indoor - temp)

    def brake_is_safe(
        self,
        indoor: float,
        outdoor: float,
        brake_duration_minutes: float,
        comfort_floor: float,
    ) -> bool:
        """Estimate whether indoor temperature remains above the comfort floor."""
        drop = self.predict_drop(indoor, outdoor, brake_duration_minutes)
        predicted = indoor - drop
        return predicted >= comfort_floor
