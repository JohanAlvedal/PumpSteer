"""Deterministic quality screening for thermal-learning observations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from ..validation import finite_float
from .models import AcceptedSample, RawRecorderSample


class ExclusionReason(StrEnum):
    """Stable reasons why an observation cannot enter a learning episode."""

    MISSING_INDOOR = "missing_indoor"
    MISSING_OUTDOOR = "missing_outdoor"
    MISSING_TARGET = "missing_target"
    MISSING_SOURCE_TIMESTAMP = "missing_source_timestamp"
    NONFINITE_VALUE = "nonfinite_value"
    SOURCE_FROM_FUTURE = "source_from_future"
    STALE_SOURCE = "stale_source"
    DUPLICATE_TIME = "duplicate_time"
    NON_MONOTONIC_TIME = "non_monotonic_time"
    NO_NEW_CRITICAL_OBSERVATION = "no_new_critical_observation"
    SOURCE_TIME_REGRESSION = "source_time_regression"
    EXCESSIVE_GAP = "excessive_gap"
    IMPLAUSIBLE_INDOOR_TEMPERATURE = "implausible_indoor_temperature"
    IMPLAUSIBLE_OUTDOOR_TEMPERATURE = "implausible_outdoor_temperature"
    IMPLAUSIBLE_TARGET_TEMPERATURE = "implausible_target_temperature"
    IMPLAUSIBLE_OPTIONAL_VALUE = "implausible_optional_value"
    IMPLAUSIBLE_INDOOR_RATE = "implausible_indoor_rate"
    MANUAL_TARGET_CHANGE = "manual_target_change"
    WINDOW_OPENING_SUSPECTED = "window_opening_suspected"


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    """Conservative, non-learned screening thresholds."""

    maximum_source_age: timedelta = timedelta(minutes=10)
    maximum_gap: timedelta = timedelta(minutes=20)
    minimum_indoor_c: float = 5.0
    maximum_indoor_c: float = 35.0
    minimum_outdoor_c: float = -50.0
    maximum_outdoor_c: float = 50.0
    minimum_target_c: float = 5.0
    maximum_target_c: float = 35.0
    minimum_virtual_output_c: float = -50.0
    maximum_virtual_output_c: float = 50.0
    maximum_heating_power_kw: float = 100.0
    minimum_supply_temperature_c: float = 0.0
    maximum_supply_temperature_c: float = 100.0
    maximum_indoor_rate_c_per_hour: float = 4.0
    target_change_tolerance_c: float = 0.05
    window_opening_rate_c_per_hour: float = -1.5
    window_opening_minimum_delta_c: float = 5.0

    def __post_init__(self) -> None:
        if not isinstance(self.maximum_source_age, timedelta):
            raise TypeError("maximum_source_age must be a timedelta")
        if not isinstance(self.maximum_gap, timedelta):
            raise TypeError("maximum_gap must be a timedelta")
        if self.maximum_source_age <= timedelta(0):
            raise ValueError("maximum_source_age must be positive")
        if self.maximum_gap <= timedelta(0):
            raise ValueError("maximum_gap must be positive")
        for field_name in (
            "minimum_indoor_c",
            "maximum_indoor_c",
            "minimum_outdoor_c",
            "maximum_outdoor_c",
            "minimum_target_c",
            "maximum_target_c",
            "minimum_virtual_output_c",
            "maximum_virtual_output_c",
            "maximum_heating_power_kw",
            "minimum_supply_temperature_c",
            "maximum_supply_temperature_c",
            "maximum_indoor_rate_c_per_hour",
            "target_change_tolerance_c",
            "window_opening_rate_c_per_hour",
            "window_opening_minimum_delta_c",
        ):
            object.__setattr__(
                self,
                field_name,
                finite_float(getattr(self, field_name), field_name),
            )
        if self.minimum_indoor_c >= self.maximum_indoor_c:
            raise ValueError("indoor temperature bounds are invalid")
        if self.minimum_outdoor_c >= self.maximum_outdoor_c:
            raise ValueError("outdoor temperature bounds are invalid")
        if self.minimum_target_c >= self.maximum_target_c:
            raise ValueError("target temperature bounds are invalid")
        if self.maximum_indoor_rate_c_per_hour <= 0:
            raise ValueError("maximum_indoor_rate_c_per_hour must be positive")
        if self.maximum_heating_power_kw <= 0:
            raise ValueError("maximum_heating_power_kw must be positive")
        if self.minimum_virtual_output_c >= self.maximum_virtual_output_c:
            raise ValueError("virtual output bounds are invalid")
        if self.minimum_supply_temperature_c >= self.maximum_supply_temperature_c:
            raise ValueError("supply temperature bounds are invalid")
        if self.target_change_tolerance_c < 0:
            raise ValueError("target_change_tolerance_c must be non-negative")
        if self.window_opening_rate_c_per_hour >= 0:
            raise ValueError("window_opening_rate_c_per_hour must be negative")
        if self.window_opening_minimum_delta_c <= 0:
            raise ValueError("window_opening_minimum_delta_c must be positive")


@dataclass(frozen=True, slots=True)
class ScreenedSample:
    """Quality result for one raw observation."""

    raw: RawRecorderSample
    accepted: AcceptedSample | None
    reasons: tuple[ExclusionReason, ...]

    @property
    def is_accepted(self) -> bool:
        return self.accepted is not None


def screen_sample(
    raw: RawRecorderSample,
    *,
    policy: QualityPolicy = QualityPolicy(),
    previous_raw: RawRecorderSample | None = None,
    previous_accepted: AcceptedSample | None = None,
) -> ScreenedSample:
    """Screen one observation without estimating any thermal parameter."""
    if not isinstance(raw, RawRecorderSample):
        raise TypeError("raw must be a RawRecorderSample")
    reasons: list[ExclusionReason] = []

    _check_required(raw, reasons)
    _check_finite(raw, reasons)
    _check_source_times(raw, policy, reasons)
    _check_ranges(raw, policy, reasons)

    if previous_raw is not None:
        if raw.captured_at == previous_raw.captured_at:
            reasons.append(ExclusionReason.DUPLICATE_TIME)
        elif raw.captured_at < previous_raw.captured_at:
            reasons.append(ExclusionReason.NON_MONOTONIC_TIME)
        elif raw.captured_at - previous_raw.captured_at > policy.maximum_gap:
            reasons.append(ExclusionReason.EXCESSIVE_GAP)
        _check_critical_source_progress(raw, previous_raw, reasons)

    if previous_accepted is not None and not _required_value_problem(reasons):
        if (
            abs(raw.target_temperature_c - previous_accepted.target_temperature_c)
            > policy.target_change_tolerance_c
        ):
            reasons.append(ExclusionReason.MANUAL_TARGET_CHANGE)
        elapsed_h = (
            raw.captured_at - previous_accepted.captured_at
        ).total_seconds() / 3600.0
        if elapsed_h > 0:
            rate = (
                raw.indoor_temperature_c - previous_accepted.indoor_temperature_c
            ) / elapsed_h
            if abs(rate) > policy.maximum_indoor_rate_c_per_hour:
                reasons.append(ExclusionReason.IMPLAUSIBLE_INDOOR_RATE)
            elif (
                rate <= policy.window_opening_rate_c_per_hour
                and raw.indoor_temperature_c - raw.outdoor_temperature_c
                >= policy.window_opening_minimum_delta_c
            ):
                reasons.append(ExclusionReason.WINDOW_OPENING_SUSPECTED)

    unique_reasons = tuple(dict.fromkeys(reasons))
    if unique_reasons:
        return ScreenedSample(raw=raw, accepted=None, reasons=unique_reasons)
    accepted = AcceptedSample(
        captured_at=raw.captured_at,
        indoor_temperature_c=raw.indoor_temperature_c,
        outdoor_temperature_c=raw.outdoor_temperature_c,
        target_temperature_c=raw.target_temperature_c,
        indoor_observed_at=raw.indoor_observed_at,
        outdoor_observed_at=raw.outdoor_observed_at,
        virtual_output_c=raw.virtual_output_c,
        virtual_output_observed_at=raw.virtual_output_observed_at,
        heating_power_kw=raw.heating_power_kw,
        heating_power_observed_at=raw.heating_power_observed_at,
        supply_temperature_c=raw.supply_temperature_c,
        supply_temperature_observed_at=raw.supply_temperature_observed_at,
    )
    return ScreenedSample(raw=raw, accepted=accepted, reasons=())


def _check_required(raw: RawRecorderSample, reasons: list[ExclusionReason]) -> None:
    for value, reason in (
        (raw.indoor_temperature_c, ExclusionReason.MISSING_INDOOR),
        (raw.outdoor_temperature_c, ExclusionReason.MISSING_OUTDOOR),
        (raw.target_temperature_c, ExclusionReason.MISSING_TARGET),
    ):
        if value is None:
            reasons.append(reason)
    if raw.indoor_observed_at is None or raw.outdoor_observed_at is None:
        reasons.append(ExclusionReason.MISSING_SOURCE_TIMESTAMP)


def _check_finite(raw: RawRecorderSample, reasons: list[ExclusionReason]) -> None:
    values = (
        raw.indoor_temperature_c,
        raw.outdoor_temperature_c,
        raw.target_temperature_c,
        raw.virtual_output_c,
        raw.heating_power_kw,
        raw.supply_temperature_c,
    )
    if any(value is not None and not _finite(value) for value in values):
        reasons.append(ExclusionReason.NONFINITE_VALUE)


def _check_source_times(
    raw: RawRecorderSample,
    policy: QualityPolicy,
    reasons: list[ExclusionReason],
) -> None:
    pairs = (
        (raw.indoor_temperature_c, raw.indoor_observed_at, False),
        (raw.outdoor_temperature_c, raw.outdoor_observed_at, False),
        (raw.virtual_output_c, raw.virtual_output_observed_at, True),
        (raw.heating_power_kw, raw.heating_power_observed_at, True),
        (raw.supply_temperature_c, raw.supply_temperature_observed_at, True),
    )
    for value, observed_at, optional in pairs:
        if value is None:
            if optional and observed_at is not None:
                reasons.append(ExclusionReason.IMPLAUSIBLE_OPTIONAL_VALUE)
            continue
        if observed_at is None:
            reasons.append(ExclusionReason.MISSING_SOURCE_TIMESTAMP)
        elif observed_at > raw.captured_at:
            reasons.append(ExclusionReason.SOURCE_FROM_FUTURE)
        elif raw.captured_at - observed_at > policy.maximum_source_age:
            reasons.append(ExclusionReason.STALE_SOURCE)


def _check_critical_source_progress(
    raw: RawRecorderSample,
    previous: RawRecorderSample,
    reasons: list[ExclusionReason],
) -> None:
    """Allow one carried-forward source while requiring some new information.

    Joined Recorder histories commonly update indoor and outdoor sensors at
    different times. A repeated timestamp for one critical source is valid when
    the other source advanced. A regression by either source is never valid.
    """
    current_times = (raw.indoor_observed_at, raw.outdoor_observed_at)
    previous_times = (
        previous.indoor_observed_at,
        previous.outdoor_observed_at,
    )
    if any(
        current is not None and old is not None and current < old
        for current, old in zip(current_times, previous_times)
    ):
        reasons.append(ExclusionReason.SOURCE_TIME_REGRESSION)
        return
    if all(
        current is not None and old is not None and current == old
        for current, old in zip(current_times, previous_times)
    ):
        reasons.append(ExclusionReason.NO_NEW_CRITICAL_OBSERVATION)


def _check_ranges(
    raw: RawRecorderSample,
    policy: QualityPolicy,
    reasons: list[ExclusionReason],
) -> None:
    if _finite(raw.indoor_temperature_c) and not (
        policy.minimum_indoor_c <= raw.indoor_temperature_c <= policy.maximum_indoor_c
    ):
        reasons.append(ExclusionReason.IMPLAUSIBLE_INDOOR_TEMPERATURE)
    if _finite(raw.outdoor_temperature_c) and not (
        policy.minimum_outdoor_c
        <= raw.outdoor_temperature_c
        <= policy.maximum_outdoor_c
    ):
        reasons.append(ExclusionReason.IMPLAUSIBLE_OUTDOOR_TEMPERATURE)
    if _finite(raw.target_temperature_c) and not (
        policy.minimum_target_c <= raw.target_temperature_c <= policy.maximum_target_c
    ):
        reasons.append(ExclusionReason.IMPLAUSIBLE_TARGET_TEMPERATURE)
    optional_valid = (
        (
            raw.virtual_output_c is None
            or (
                _finite(raw.virtual_output_c)
                and policy.minimum_virtual_output_c
                <= raw.virtual_output_c
                <= policy.maximum_virtual_output_c
            )
        )
        and (
            raw.heating_power_kw is None
            or (
                _finite(raw.heating_power_kw)
                and 0.0 <= raw.heating_power_kw <= policy.maximum_heating_power_kw
            )
        )
        and (
            raw.supply_temperature_c is None
            or (
                _finite(raw.supply_temperature_c)
                and policy.minimum_supply_temperature_c
                <= raw.supply_temperature_c
                <= policy.maximum_supply_temperature_c
            )
        )
    )
    if not optional_valid:
        reasons.append(ExclusionReason.IMPLAUSIBLE_OPTIONAL_VALUE)


def _required_value_problem(reasons: list[ExclusionReason]) -> bool:
    return any(
        reason
        in {
            ExclusionReason.MISSING_INDOOR,
            ExclusionReason.MISSING_OUTDOOR,
            ExclusionReason.MISSING_TARGET,
            ExclusionReason.NONFINITE_VALUE,
        }
        for reason in reasons
    )


def _finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
