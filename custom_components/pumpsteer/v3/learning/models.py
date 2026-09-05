"""Immutable observations used by the V3 learning ingestion boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..validation import aware_datetime, finite_float


@dataclass(frozen=True, slots=True)
class RawRecorderSample:
    """Untrusted values read from a Recorder-like history source.

    Numeric fields deliberately accept missing and non-finite values so the
    screening stage can assign stable exclusion reasons instead of failing an
    entire history import. Timestamps must still be valid UTC datetimes because
    ordering cannot be recovered safely from ambiguous time.
    """

    captured_at: datetime
    indoor_temperature_c: float | None
    outdoor_temperature_c: float | None
    target_temperature_c: float | None
    indoor_observed_at: datetime | None
    outdoor_observed_at: datetime | None
    virtual_output_c: float | None = None
    virtual_output_observed_at: datetime | None = None
    heating_power_kw: float | None = None
    heating_power_observed_at: datetime | None = None
    supply_temperature_c: float | None = None
    supply_temperature_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "captured_at", _utc(self.captured_at, "captured_at"))
        for field_name in (
            "indoor_observed_at",
            "outdoor_observed_at",
            "virtual_output_observed_at",
            "heating_power_observed_at",
            "supply_temperature_observed_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _utc(value, field_name))


@dataclass(frozen=True, slots=True)
class RawTimelineBoundary:
    """Compact raw ordering context safe to retain between ingestion batches.

    Values are deliberately absent. Quality screening only needs these three
    timestamps to enforce capture ordering and critical-source progress across
    a batch boundary.
    """

    captured_at: datetime
    indoor_observed_at: datetime | None
    outdoor_observed_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "captured_at", _utc(self.captured_at, "captured_at"))
        for field_name in ("indoor_observed_at", "outdoor_observed_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _utc(value, field_name))

    @classmethod
    def from_sample(cls, sample: RawRecorderSample) -> RawTimelineBoundary:
        """Retain only the ordering fields needed from an untrusted sample."""
        if not isinstance(sample, RawRecorderSample):
            raise TypeError("sample must be a RawRecorderSample")
        return cls(
            captured_at=sample.captured_at,
            indoor_observed_at=sample.indoor_observed_at,
            outdoor_observed_at=sample.outdoor_observed_at,
        )


@dataclass(frozen=True, slots=True)
class AcceptedSample:
    """A finite, normalized sample approved for an uncontaminated episode."""

    captured_at: datetime
    indoor_temperature_c: float
    outdoor_temperature_c: float
    target_temperature_c: float
    indoor_observed_at: datetime
    outdoor_observed_at: datetime
    virtual_output_c: float | None = None
    virtual_output_observed_at: datetime | None = None
    heating_power_kw: float | None = None
    heating_power_observed_at: datetime | None = None
    supply_temperature_c: float | None = None
    supply_temperature_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "captured_at", _utc(self.captured_at, "captured_at"))
        for field_name in ("indoor_observed_at", "outdoor_observed_at"):
            object.__setattr__(
                self, field_name, _utc(getattr(self, field_name), field_name)
            )
        for field_name in (
            "indoor_temperature_c",
            "outdoor_temperature_c",
            "target_temperature_c",
        ):
            object.__setattr__(
                self, field_name, finite_float(getattr(self, field_name), field_name)
            )
        for field_name in (
            "virtual_output_c",
            "heating_power_kw",
            "supply_temperature_c",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, finite_float(value, field_name))
        for value_name, timestamp_name in (
            ("virtual_output_c", "virtual_output_observed_at"),
            ("heating_power_kw", "heating_power_observed_at"),
            ("supply_temperature_c", "supply_temperature_observed_at"),
        ):
            value = getattr(self, value_name)
            timestamp = getattr(self, timestamp_name)
            if (value is None) != (timestamp is None):
                raise ValueError(
                    f"{value_name} and {timestamp_name} must be present together"
                )
            if timestamp is not None:
                object.__setattr__(
                    self,
                    timestamp_name,
                    _utc(timestamp, timestamp_name),
                )


def _utc(value: datetime, field_name: str) -> datetime:
    result = aware_datetime(value, field_name)
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return result
