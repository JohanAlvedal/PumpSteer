"""Tests for observation-only learning quality and episode segmentation."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3.learning import (
    ExclusionReason,
    QualityPolicy,
    RawRecorderSample,
    screen_sample,
    segment_episodes,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def sample(
    minute: int = 0,
    *,
    indoor: float | None = 21.0,
    outdoor: float | None = -5.0,
    target: float | None = 21.0,
    source_age: timedelta = timedelta(0),
    virtual: float | None = -7.0,
    power: float | None = 2.0,
    supply: float | None = 35.0,
) -> RawRecorderSample:
    captured = NOW + timedelta(minutes=minute)
    observed = captured - source_age
    return RawRecorderSample(
        captured_at=captured,
        indoor_temperature_c=indoor,
        outdoor_temperature_c=outdoor,
        target_temperature_c=target,
        indoor_observed_at=observed if indoor is not None else None,
        outdoor_observed_at=observed if outdoor is not None else None,
        virtual_output_c=virtual,
        virtual_output_observed_at=observed if virtual is not None else None,
        heating_power_kw=power,
        heating_power_observed_at=observed if power is not None else None,
        supply_temperature_c=supply,
        supply_temperature_observed_at=observed if supply is not None else None,
    )


def reasons(raw: RawRecorderSample, previous=None, previous_accepted=None):
    return screen_sample(
        raw, previous_raw=previous, previous_accepted=previous_accepted
    ).reasons


def test_clean_samples_form_one_deterministic_episode() -> None:
    data = [sample(0), sample(5, indoor=20.95), sample(10, indoor=20.9)]

    first = segment_episodes(data)
    second = segment_episodes(data)

    assert first == second
    assert len(first.episodes) == 1
    assert len(first.episodes[0].samples) == 3
    assert first.excluded == ()
    accepted = first.episodes[0].samples[0]
    assert accepted.virtual_output_observed_at == NOW
    assert accepted.heating_power_observed_at == NOW
    assert accepted.supply_temperature_observed_at == NOW


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (sample(indoor=None), ExclusionReason.MISSING_INDOOR),
        (sample(outdoor=None), ExclusionReason.MISSING_OUTDOOR),
        (sample(target=None), ExclusionReason.MISSING_TARGET),
        (sample(indoor=float("nan")), ExclusionReason.NONFINITE_VALUE),
        (sample(source_age=timedelta(minutes=11)), ExclusionReason.STALE_SOURCE),
        (sample(indoor=40.0), ExclusionReason.IMPLAUSIBLE_INDOOR_TEMPERATURE),
        (sample(outdoor=-60.0), ExclusionReason.IMPLAUSIBLE_OUTDOOR_TEMPERATURE),
        (sample(target=40.0), ExclusionReason.IMPLAUSIBLE_TARGET_TEMPERATURE),
        (sample(power=-1.0), ExclusionReason.IMPLAUSIBLE_OPTIONAL_VALUE),
    ],
)
def test_base_exclusion_paths(raw: RawRecorderSample, reason: ExclusionReason) -> None:
    assert reason in reasons(raw)


def test_missing_optional_source_timestamp_is_excluded() -> None:
    raw = sample()
    raw = RawRecorderSample(
        captured_at=raw.captured_at,
        indoor_temperature_c=raw.indoor_temperature_c,
        outdoor_temperature_c=raw.outdoor_temperature_c,
        target_temperature_c=raw.target_temperature_c,
        indoor_observed_at=raw.indoor_observed_at,
        outdoor_observed_at=raw.outdoor_observed_at,
        virtual_output_c=-7.0,
        virtual_output_observed_at=None,
    )

    assert ExclusionReason.MISSING_SOURCE_TIMESTAMP in reasons(raw)


def test_optional_timestamp_without_value_is_excluded() -> None:
    raw = sample(virtual=None)
    raw = RawRecorderSample(
        captured_at=raw.captured_at,
        indoor_temperature_c=raw.indoor_temperature_c,
        outdoor_temperature_c=raw.outdoor_temperature_c,
        target_temperature_c=raw.target_temperature_c,
        indoor_observed_at=raw.indoor_observed_at,
        outdoor_observed_at=raw.outdoor_observed_at,
        virtual_output_c=None,
        virtual_output_observed_at=raw.captured_at,
    )

    assert ExclusionReason.IMPLAUSIBLE_OPTIONAL_VALUE in reasons(raw)


def test_future_source_timestamp_is_excluded() -> None:
    raw = sample()
    future = raw.captured_at + timedelta(seconds=1)
    raw = RawRecorderSample(
        captured_at=raw.captured_at,
        indoor_temperature_c=21.0,
        outdoor_temperature_c=-5.0,
        target_temperature_c=21.0,
        indoor_observed_at=future,
        outdoor_observed_at=raw.captured_at,
    )

    assert ExclusionReason.SOURCE_FROM_FUTURE in reasons(raw)


@pytest.mark.parametrize(
    ("minute", "reason"),
    [
        (0, ExclusionReason.DUPLICATE_TIME),
        (-1, ExclusionReason.NON_MONOTONIC_TIME),
        (21, ExclusionReason.EXCESSIVE_GAP),
    ],
)
def test_timeline_exclusion_paths(minute: int, reason: ExclusionReason) -> None:
    previous = sample(0)

    assert reason in reasons(sample(minute), previous=previous)


@pytest.mark.parametrize(
    ("source_minute", "reason"),
    [
        (0, ExclusionReason.DUPLICATE_SOURCE_TIME),
        (-1, ExclusionReason.NON_MONOTONIC_SOURCE_TIME),
    ],
)
def test_critical_source_timeline_exclusion_paths(
    source_minute: int,
    reason: ExclusionReason,
) -> None:
    previous = sample(0)
    current = sample(5)
    current_source_time = NOW + timedelta(minutes=source_minute)
    current = RawRecorderSample(
        captured_at=current.captured_at,
        indoor_temperature_c=current.indoor_temperature_c,
        outdoor_temperature_c=current.outdoor_temperature_c,
        target_temperature_c=current.target_temperature_c,
        indoor_observed_at=current_source_time,
        outdoor_observed_at=current.outdoor_observed_at,
        virtual_output_c=current.virtual_output_c,
        virtual_output_observed_at=current.virtual_output_observed_at,
        heating_power_kw=current.heating_power_kw,
        heating_power_observed_at=current.heating_power_observed_at,
        supply_temperature_c=current.supply_temperature_c,
        supply_temperature_observed_at=current.supply_temperature_observed_at,
    )

    assert reason in reasons(current, previous=previous)


def test_implausible_indoor_rate_is_excluded() -> None:
    previous_result = screen_sample(sample(0))
    raw = sample(5, indoor=20.0)

    assert ExclusionReason.IMPLAUSIBLE_INDOOR_RATE in reasons(
        raw, previous=sample(0), previous_accepted=previous_result.accepted
    )


def test_manual_target_change_is_excluded() -> None:
    previous_result = screen_sample(sample(0))

    assert ExclusionReason.MANUAL_TARGET_CHANGE in reasons(
        sample(5, target=22.0),
        previous=sample(0),
        previous_accepted=previous_result.accepted,
    )


def test_obvious_window_opening_cooling_is_contaminated() -> None:
    previous_result = screen_sample(sample(0))
    raw = sample(15, indoor=20.6)

    assert ExclusionReason.WINDOW_OPENING_SUSPECTED in reasons(
        raw, previous=sample(0), previous_accepted=previous_result.accepted
    )


def test_excluded_sample_splits_clean_episodes() -> None:
    data = [
        sample(0),
        sample(5, indoor=20.95),
        sample(10, target=22.0),
        sample(15, indoor=20.9, target=22.0),
        sample(20, indoor=20.85, target=22.0),
    ]

    batch = segment_episodes(data)

    assert [len(episode.samples) for episode in batch.episodes] == [2, 2]
    assert len(batch.excluded) == 1
    assert ExclusionReason.MANUAL_TARGET_CHANGE in batch.excluded[0].reasons


def test_raw_timestamps_must_be_timezone_aware_utc() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RawRecorderSample(
            captured_at=datetime(2026, 1, 15, 12, 0),
            indoor_temperature_c=21.0,
            outdoor_temperature_c=-5.0,
            target_temperature_c=21.0,
            indoor_observed_at=NOW,
            outdoor_observed_at=NOW,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_indoor_rate_c_per_hour", float("nan")),
        ("maximum_heating_power_kw", 0.0),
        ("window_opening_minimum_delta_c", -1.0),
    ],
)
def test_quality_policy_rejects_invalid_thresholds(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        QualityPolicy(**{field: value})
