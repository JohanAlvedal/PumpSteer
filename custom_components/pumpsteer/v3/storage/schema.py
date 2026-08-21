"""Immutable schema objects for PumpSteer V3 checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..control.engine import EngineState
from ..validation import aware_datetime, finite_float


CURRENT_SCHEMA_VERSION = 1
MIN_TARGET_TEMPERATURE = 5.0
MAX_TARGET_TEMPERATURE = 35.0


@dataclass(frozen=True, slots=True)
class PersistedState:
    """Complete non-learned state required for deterministic restart.

    Learned thermal parameters are intentionally absent. A future learned-model
    checkpoint must include its evidence, uncertainty, validity domain, and model
    schema; a bare learned parameter is never sufficient.
    """

    schema_version: int
    algorithm_version: str
    saved_at: datetime
    target_temperature: float
    preset: str
    engine_state: EngineState

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise TypeError("schema_version must be an integer")
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CURRENT_SCHEMA_VERSION} after migration"
            )
        if (
            not isinstance(self.algorithm_version, str)
            or not self.algorithm_version.strip()
        ):
            raise ValueError("algorithm_version must be a non-empty string")
        object.__setattr__(self, "saved_at", _utc(self.saved_at, "saved_at"))
        object.__setattr__(
            self,
            "target_temperature",
            finite_float(self.target_temperature, "target_temperature"),
        )
        if (
            not MIN_TARGET_TEMPERATURE
            <= self.target_temperature
            <= MAX_TARGET_TEMPERATURE
        ):
            raise ValueError("target_temperature must be between 5 and 35 °C")
        if not isinstance(self.preset, str) or not self.preset.strip():
            raise ValueError("preset must be a non-empty string")
        if not isinstance(self.engine_state, EngineState):
            raise TypeError("engine_state must be an EngineState")
        for field_name in ("last_indoor_observed_at", "last_outdoor_observed_at"):
            value = getattr(self.engine_state, field_name)
            if value is not None:
                _utc(value, f"engine_state.{field_name}")
                if value > self.saved_at:
                    raise ValueError(
                        f"engine_state.{field_name} cannot be later than saved_at"
                    )
        timeline = {
            "engine_state.comfort.last_step_at": self.engine_state.comfort.last_step_at,
            "engine_state.previous_output.decision.decided_at": (
                self.engine_state.previous_output.decision.decided_at
                if self.engine_state.previous_output is not None
                else None
            ),
        }
        for field_name, value in timeline.items():
            if value is not None and value > self.saved_at:
                raise ValueError(f"{field_name} cannot be later than saved_at")


def _utc(value: datetime, field_name: str) -> datetime:
    result = aware_datetime(value, field_name)
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return result
