"""Immutable observation-learning checkpoint schema without control authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..validation import aware_datetime, finite_float
from .episodes import EpisodeBoundary

LEARNING_CHECKPOINT_SCHEMA_VERSION = 1
LEARNING_PIPELINE_VERSION = "observation-v1"
MAX_TARGET_EPOCHS = 256
MIN_TARGET_TEMPERATURE_C = 5.0
MAX_TARGET_TEMPERATURE_C = 35.0


@dataclass(frozen=True, slots=True)
class TargetEpoch:
    """One half-open interval in the user target timeline."""

    started_at: datetime
    target_temperature_c: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", _utc(self.started_at, "started_at"))
        target = finite_float(self.target_temperature_c, "target_temperature_c")
        if not MIN_TARGET_TEMPERATURE_C <= target <= MAX_TARGET_TEMPERATURE_C:
            raise ValueError("target_temperature_c must be between 5 and 35 °C")
        object.__setattr__(self, "target_temperature_c", target)


@dataclass(frozen=True, slots=True)
class LearningCheckpoint:
    """Durable ingestion position and minimal cross-batch screening context.

    This schema intentionally cannot represent learned parameters, confidence,
    planning authority, controller state, or physical output.
    """

    schema_version: int
    pipeline_version: str
    entry_id: str
    saved_at: datetime
    indoor_entity_id: str
    outdoor_entity_id: str
    cursor_at: datetime
    target_timeline: tuple[TargetEpoch, ...]
    boundary: EpisodeBoundary = field(default_factory=EpisodeBoundary)

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise TypeError("schema_version must be an integer")
        if self.schema_version != LEARNING_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must match the current learning checkpoint schema"
            )
        if self.pipeline_version != LEARNING_PIPELINE_VERSION:
            raise ValueError("pipeline_version is not supported")
        for field_name in ("entry_id", "indoor_entity_id", "outdoor_entity_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.indoor_entity_id == self.outdoor_entity_id:
            raise ValueError("indoor and outdoor entities must be distinct")

        saved_at = _utc(self.saved_at, "saved_at")
        cursor_at = _utc(self.cursor_at, "cursor_at")
        object.__setattr__(self, "saved_at", saved_at)
        object.__setattr__(self, "cursor_at", cursor_at)
        if cursor_at > saved_at:
            raise ValueError("cursor_at cannot be later than saved_at")

        if not isinstance(self.target_timeline, tuple):
            raise TypeError("target_timeline must be a tuple")
        if not 1 <= len(self.target_timeline) <= MAX_TARGET_EPOCHS:
            raise ValueError("target_timeline must contain between 1 and 256 epochs")
        previous_started_at: datetime | None = None
        for epoch in self.target_timeline:
            if not isinstance(epoch, TargetEpoch):
                raise TypeError("target_timeline must contain TargetEpoch values")
            if (
                previous_started_at is not None
                and epoch.started_at <= previous_started_at
            ):
                raise ValueError("target_timeline must be strictly ordered")
            if epoch.started_at > saved_at:
                raise ValueError("target epoch cannot be later than saved_at")
            previous_started_at = epoch.started_at
        if self.target_timeline[0].started_at > cursor_at:
            raise ValueError("the first target epoch must start at or before cursor_at")

        if not isinstance(self.boundary, EpisodeBoundary):
            raise TypeError("boundary must be an EpisodeBoundary")
        raw = self.boundary.previous_raw
        accepted = self.boundary.previous_accepted
        if raw is not None:
            if raw.captured_at >= cursor_at:
                raise ValueError("boundary raw position must precede cursor_at")
            for name in ("indoor_observed_at", "outdoor_observed_at"):
                observed_at = getattr(raw, name)
                if observed_at is not None and observed_at > raw.captured_at:
                    raise ValueError(f"boundary {name} cannot follow captured_at")

        active_cursor_epoch = self.target_epoch_at(cursor_at)
        if raw is not None and raw.captured_at < active_cursor_epoch.started_at:
            raise ValueError("boundary cannot cross the active target epoch")
        if accepted is not None:
            _validate_accepted_boundary(accepted)
            active_sample_epoch = self.target_epoch_at(accepted.captured_at)
            if (
                accepted.target_temperature_c
                != active_sample_epoch.target_temperature_c
            ):
                raise ValueError(
                    "accepted boundary target does not match the active target epoch"
                )
            if self.boundary.open_episode_started_at < active_sample_epoch.started_at:
                raise ValueError("open episode cannot cross a target epoch")

    def target_epoch_at(self, timestamp: datetime) -> TargetEpoch:
        """Return the latest target epoch at a UTC timestamp."""
        timestamp = _utc(timestamp, "timestamp")
        active: TargetEpoch | None = None
        for epoch in self.target_timeline:
            if epoch.started_at > timestamp:
                break
            active = epoch
        if active is None:
            raise ValueError("timestamp precedes the target timeline")
        return active


def _validate_accepted_boundary(sample: object) -> None:
    ranges = (
        ("indoor_temperature_c", 5.0, 35.0),
        ("outdoor_temperature_c", -50.0, 50.0),
        ("target_temperature_c", 5.0, 35.0),
    )
    for field_name, minimum, maximum in ranges:
        value = finite_float(getattr(sample, field_name), field_name)
        if not minimum <= value <= maximum:
            raise ValueError(f"{field_name} is outside the checkpoint range")
    for field_name in (
        "indoor_observed_at",
        "outdoor_observed_at",
        "virtual_output_observed_at",
        "heating_power_observed_at",
        "supply_temperature_observed_at",
    ):
        observed_at = getattr(sample, field_name)
        if observed_at is not None and observed_at > sample.captured_at:
            raise ValueError(f"accepted {field_name} cannot follow captured_at")
    optional_ranges = (
        ("virtual_output_c", -50.0, 50.0),
        ("heating_power_kw", 0.0, 100.0),
        ("supply_temperature_c", 0.0, 100.0),
    )
    for field_name, minimum, maximum in optional_ranges:
        value = getattr(sample, field_name)
        if (
            value is not None
            and not minimum <= finite_float(value, field_name) <= maximum
        ):
            raise ValueError(f"{field_name} is outside the checkpoint range")


def _utc(value: datetime, field_name: str) -> datetime:
    result = aware_datetime(value, field_name)
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return result
