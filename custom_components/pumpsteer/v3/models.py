"""Immutable domain objects and control contracts for PumpSteer V3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .enums import ControlState, LearningStage, ReasonCode, Unit
from .validation import aware_datetime, finite_float, supported_unit


@dataclass(frozen=True, slots=True)
class SensorReading:
    """A unit-bearing sensor sample captured at a known instant."""

    value: float
    observed_at: datetime
    unit: Unit
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", finite_float(self.value, "value"))
        object.__setattr__(
            self, "observed_at", aware_datetime(self.observed_at, "observed_at")
        )
        object.__setattr__(self, "unit", supported_unit(self.unit))
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")

    def age_at(self, instant: datetime) -> timedelta:
        """Return sample age and reject observations from the future."""
        instant = aware_datetime(instant, "instant")
        age = instant - self.observed_at
        if age < timedelta(0):
            raise ValueError("observed_at cannot be later than instant")
        return age


@dataclass(frozen=True, slots=True)
class Observation:
    """Normalized inputs for one deterministic control cycle."""

    captured_at: datetime
    indoor: SensorReading
    outdoor: SensorReading
    electricity_price: SensorReading | None = None
    forecast_outdoor: tuple[SensorReading, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "captured_at", aware_datetime(self.captured_at, "captured_at")
        )
        self._require_unit(self.indoor, Unit.CELSIUS, "indoor")
        self._require_unit(self.outdoor, Unit.CELSIUS, "outdoor")
        if self.electricity_price is not None:
            self._require_unit(
                self.electricity_price, Unit.SEK_PER_KWH, "electricity_price"
            )
        forecast = tuple(self.forecast_outdoor)
        for index, reading in enumerate(forecast):
            self._require_unit(reading, Unit.CELSIUS, f"forecast_outdoor[{index}]")
        object.__setattr__(self, "forecast_outdoor", forecast)

    @staticmethod
    def _require_unit(reading: SensorReading, unit: Unit, field_name: str) -> None:
        if not isinstance(reading, SensorReading):
            raise TypeError(f"{field_name} must be a SensorReading")
        if reading.unit is not unit:
            raise ValueError(f"{field_name} must use {unit.value}")

    def comfort_error(self, target_temperature: float) -> float:
        """Return target minus indoor temperature; positive means too cold."""
        target = finite_float(target_temperature, "target_temperature")
        return target - self.indoor.value


@dataclass(frozen=True, slots=True)
class ComfortPolicy:
    """User intent and automatic comfort boundaries."""

    target_temperature: float = 21.0
    minimum_temperature: float = 19.5
    maximum_temperature: float = 23.0

    def __post_init__(self) -> None:
        for field_name in (
            "target_temperature",
            "minimum_temperature",
            "maximum_temperature",
        ):
            object.__setattr__(
                self, field_name, finite_float(getattr(self, field_name), field_name)
            )
        if self.minimum_temperature > self.target_temperature:
            raise ValueError("minimum_temperature cannot exceed target_temperature")
        if self.target_temperature > self.maximum_temperature:
            raise ValueError("target_temperature cannot exceed maximum_temperature")


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    """Non-learned hard limits that always constrain controller output."""

    minimum_virtual_temperature: float = -30.0
    maximum_virtual_temperature: float = 30.0
    maximum_heating_request: float = 15.0
    maximum_curtailment: float = 15.0
    maximum_sensor_age: timedelta = timedelta(minutes=10)

    def __post_init__(self) -> None:
        for field_name in (
            "minimum_virtual_temperature",
            "maximum_virtual_temperature",
            "maximum_heating_request",
            "maximum_curtailment",
        ):
            object.__setattr__(
                self, field_name, finite_float(getattr(self, field_name), field_name)
            )
        if self.minimum_virtual_temperature >= self.maximum_virtual_temperature:
            raise ValueError(
                "minimum_virtual_temperature must be below maximum_virtual_temperature"
            )
        if self.maximum_heating_request < 0 or self.maximum_curtailment < 0:
            raise ValueError("request and curtailment limits must be non-negative")
        if not isinstance(self.maximum_sensor_age, timedelta):
            raise TypeError("maximum_sensor_age must be a timedelta")
        if self.maximum_sensor_age <= timedelta(0):
            raise ValueError("maximum_sensor_age must be positive")


@dataclass(frozen=True, slots=True)
class ModelConfidence:
    """Explainable evidence level for the learned thermal model."""

    stage: LearningStage = LearningStage.UNINITIALIZED
    score: float = 0.0
    accepted_samples: int = 0
    validation_events: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.stage, LearningStage):
            object.__setattr__(self, "stage", LearningStage(self.stage))
        object.__setattr__(self, "score", finite_float(self.score, "score"))
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0 and 1")
        for field_name in ("accepted_samples", "validation_events"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True, slots=True)
class ControlDecision:
    """A complete, explainable output from one control cycle.

    Sign convention:
    - positive heating_request requests more heat;
    - positive curtailment requests less heat;
    - virtual temperature equals outdoor - heating_request + curtailment.
    """

    decided_at: datetime
    state: ControlState
    outdoor_temperature: float
    heating_request: float
    curtailment: float
    virtual_temperature: float
    reason_codes: tuple[ReasonCode, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decided_at", aware_datetime(self.decided_at, "decided_at")
        )
        if not isinstance(self.state, ControlState):
            object.__setattr__(self, "state", ControlState(self.state))
        for field_name in (
            "outdoor_temperature",
            "heating_request",
            "curtailment",
            "virtual_temperature",
        ):
            object.__setattr__(
                self, field_name, finite_float(getattr(self, field_name), field_name)
            )
        if self.heating_request < 0:
            raise ValueError("heating_request must be non-negative")
        if self.curtailment < 0:
            raise ValueError("curtailment must be non-negative")
        reasons = tuple(ReasonCode(reason) for reason in self.reason_codes)
        if not reasons:
            raise ValueError("reason_codes must contain at least one reason")
        object.__setattr__(self, "reason_codes", reasons)
        expected = self.outdoor_temperature - self.heating_request + self.curtailment
        if abs(self.virtual_temperature - expected) > 1e-9:
            raise ValueError(
                "virtual_temperature must equal outdoor_temperature - "
                "heating_request + curtailment"
            )

    @classmethod
    def create(
        cls,
        *,
        decided_at: datetime,
        state: ControlState,
        outdoor_temperature: float,
        heating_request: float = 0.0,
        curtailment: float = 0.0,
        reason_codes: Iterable[ReasonCode],
    ) -> "ControlDecision":
        """Create a decision while deriving virtual temperature by contract."""
        outdoor = finite_float(outdoor_temperature, "outdoor_temperature")
        heating = finite_float(heating_request, "heating_request")
        curtailed = finite_float(curtailment, "curtailment")
        return cls(
            decided_at=decided_at,
            state=state,
            outdoor_temperature=outdoor,
            heating_request=heating,
            curtailment=curtailed,
            virtual_temperature=outdoor - heating + curtailed,
            reason_codes=tuple(reason_codes),
        )
