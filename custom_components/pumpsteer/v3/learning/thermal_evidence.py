"""Descriptive thermal evidence extracted from screened observations.

This module deliberately describes measured temperature motion only.  It does
not infer heat-pump state, delivered heat, building parameters, confidence, or
control authority.  A target temperature is user intent, not an actuator
measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from .episodes import EpisodeBatch
from .models import AcceptedSample


class ThermalTrend(StrEnum):
    """Direction of one observed indoor-temperature interval."""

    RISING_OBSERVED = "rising_observed"
    FALLING_OBSERVED = "falling_observed"
    STABLE_OBSERVED = "stable_observed"


@dataclass(frozen=True, slots=True)
class ThermalEvidencePolicy:
    """Fixed engineering thresholds, intentionally absent from user setup."""

    minimum_resolvable_change_c: float = 0.05
    target_tolerance_c: float = 0.05

    def __post_init__(self) -> None:
        for name in ("minimum_resolvable_change_c", "target_tolerance_c"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ThermalEvidenceInterval:
    """One non-overlapping, directly observed indoor-temperature interval."""

    duration_seconds: float
    indoor_change_c: float
    indoor_rate_c_per_hour: float
    mean_indoor_outdoor_delta_c: float
    mean_target_error_c: float
    trend: ThermalTrend
    virtual_output_observed: bool
    heating_power_observed: bool
    supply_temperature_observed: bool
    crosses_batch_boundary: bool = False

    def __post_init__(self) -> None:
        for name in (
            "duration_seconds",
            "indoor_change_c",
            "indoor_rate_c_per_hour",
            "mean_indoor_outdoor_delta_c",
            "mean_target_error_c",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if not isinstance(self.trend, ThermalTrend):
            raise TypeError("trend must be a ThermalTrend")
        for name in (
            "virtual_output_observed",
            "heating_power_observed",
            "supply_temperature_observed",
            "crosses_batch_boundary",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class ThermalEvidenceSummary:
    """Privacy-safe aggregate of descriptive evidence intervals."""

    interval_count: int = 0
    observed_duration_seconds: float = 0.0
    rising_interval_count: int = 0
    falling_interval_count: int = 0
    stable_interval_count: int = 0
    skipped_no_indoor_progress: int = 0
    virtual_output_interval_count: int = 0
    heating_power_interval_count: int = 0
    supply_temperature_interval_count: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.observed_duration_seconds, bool) or not isinstance(
            self.observed_duration_seconds, (int, float)
        ):
            raise TypeError("observed_duration_seconds must be numeric")
        if (
            not math.isfinite(self.observed_duration_seconds)
            or self.observed_duration_seconds < 0
        ):
            raise ValueError(
                "observed_duration_seconds must be finite and non-negative"
            )
        for name in self.__dataclass_fields__:
            if name == "observed_duration_seconds":
                continue
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if (
            self.rising_interval_count
            + self.falling_interval_count
            + self.stable_interval_count
            != self.interval_count
        ):
            raise ValueError("trend counts must equal interval_count")
        for name in (
            "virtual_output_interval_count",
            "heating_power_interval_count",
            "supply_temperature_interval_count",
        ):
            if getattr(self, name) > self.interval_count:
                raise ValueError(f"{name} cannot exceed interval_count")

    @classmethod
    def from_intervals(
        cls,
        intervals: tuple[ThermalEvidenceInterval, ...],
        *,
        skipped_no_indoor_progress: int,
    ) -> ThermalEvidenceSummary:
        return cls(
            interval_count=len(intervals),
            observed_duration_seconds=sum(
                interval.duration_seconds for interval in intervals
            ),
            rising_interval_count=sum(
                interval.trend is ThermalTrend.RISING_OBSERVED for interval in intervals
            ),
            falling_interval_count=sum(
                interval.trend is ThermalTrend.FALLING_OBSERVED
                for interval in intervals
            ),
            stable_interval_count=sum(
                interval.trend is ThermalTrend.STABLE_OBSERVED for interval in intervals
            ),
            skipped_no_indoor_progress=skipped_no_indoor_progress,
            virtual_output_interval_count=sum(
                interval.virtual_output_observed for interval in intervals
            ),
            heating_power_interval_count=sum(
                interval.heating_power_observed for interval in intervals
            ),
            supply_temperature_interval_count=sum(
                interval.supply_temperature_observed for interval in intervals
            ),
        )

    def merged(self, other: ThermalEvidenceSummary) -> ThermalEvidenceSummary:
        """Combine disjoint summaries without retaining source observations."""
        if not isinstance(other, ThermalEvidenceSummary):
            raise TypeError("other must be a ThermalEvidenceSummary")
        return ThermalEvidenceSummary(
            **{
                field: getattr(self, field) + getattr(other, field)
                for field in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True, slots=True)
class ThermalEvidenceBatch:
    """Transient interval detail plus its aggregate summary."""

    intervals: tuple[ThermalEvidenceInterval, ...]
    summary: ThermalEvidenceSummary


def extract_thermal_evidence(
    batch: EpisodeBatch,
    *,
    previous_accepted: AcceptedSample | None = None,
    policy: ThermalEvidencePolicy = ThermalEvidencePolicy(),  # noqa: B008
) -> ThermalEvidenceBatch:
    """Extract descriptive intervals without bridging episode boundaries.

    ``previous_accepted`` is used only for the first episode fragment when the
    segmenter explicitly states that it continues a previously screened
    episode.  This accounts for the cross-batch edge exactly once.
    """
    if not isinstance(batch, EpisodeBatch):
        raise TypeError("batch must be an EpisodeBatch")
    if previous_accepted is not None and not isinstance(
        previous_accepted, AcceptedSample
    ):
        raise TypeError("previous_accepted must be an AcceptedSample")
    if batch.first_episode_continues and previous_accepted is None:
        raise ValueError("continued first episode requires previous_accepted")

    intervals: list[ThermalEvidenceInterval] = []
    skipped_no_progress = 0
    for episode_index, episode in enumerate(batch.episodes):
        samples = episode.samples
        crosses_boundary = (
            episode_index == 0
            and batch.first_episode_continues
            and previous_accepted is not None
        )
        if crosses_boundary:
            samples = (previous_accepted, *samples)

        for previous, current in pairwise(samples):
            if current.captured_at <= previous.captured_at:
                raise ValueError("episode capture times must be strictly increasing")
            if current.indoor_observed_at < previous.indoor_observed_at:
                raise ValueError("indoor observation time cannot regress")
            if (
                abs(current.target_temperature_c - previous.target_temperature_c)
                > policy.target_tolerance_c
            ):
                raise ValueError("thermal evidence cannot cross a target change")

        indoor_origin_crosses_boundary = crosses_boundary
        for previous, current in pairwise(samples):
            if current.indoor_observed_at == previous.indoor_observed_at:
                if current.indoor_temperature_c != previous.indoor_temperature_c:
                    raise ValueError(
                        "indoor value cannot change without a new observation time"
                    )
                skipped_no_progress += 1
                continue

            duration = current.indoor_observed_at - previous.indoor_observed_at
            duration_seconds = duration.total_seconds()
            change = current.indoor_temperature_c - previous.indoor_temperature_c
            if change >= policy.minimum_resolvable_change_c:
                trend = ThermalTrend.RISING_OBSERVED
            elif change <= -policy.minimum_resolvable_change_c:
                trend = ThermalTrend.FALLING_OBSERVED
            else:
                trend = ThermalTrend.STABLE_OBSERVED

            intervals.append(
                ThermalEvidenceInterval(
                    duration_seconds=duration_seconds,
                    indoor_change_c=change,
                    indoor_rate_c_per_hour=change * 3600.0 / duration_seconds,
                    mean_indoor_outdoor_delta_c=(
                        (previous.indoor_temperature_c - previous.outdoor_temperature_c)
                        + (current.indoor_temperature_c - current.outdoor_temperature_c)
                    )
                    / 2.0,
                    mean_target_error_c=(
                        (previous.indoor_temperature_c - previous.target_temperature_c)
                        + (current.indoor_temperature_c - current.target_temperature_c)
                    )
                    / 2.0,
                    trend=trend,
                    virtual_output_observed=_optional_pair(
                        previous.virtual_output_c, current.virtual_output_c
                    ),
                    heating_power_observed=_optional_pair(
                        previous.heating_power_kw, current.heating_power_kw
                    ),
                    supply_temperature_observed=_optional_pair(
                        previous.supply_temperature_c,
                        current.supply_temperature_c,
                    ),
                    crosses_batch_boundary=indoor_origin_crosses_boundary,
                )
            )
            indoor_origin_crosses_boundary = False

    result = tuple(intervals)
    return ThermalEvidenceBatch(
        intervals=result,
        summary=ThermalEvidenceSummary.from_intervals(
            result,
            skipped_no_indoor_progress=skipped_no_progress,
        ),
    )


def _optional_pair(previous: float | None, current: float | None) -> bool:
    return previous is not None and current is not None
