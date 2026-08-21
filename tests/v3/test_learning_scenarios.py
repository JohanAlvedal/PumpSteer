"""Independent contamination scenarios for the V3 learning boundary."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta, timezone

import custom_components.pumpsteer.v3.learning as learning
from custom_components.pumpsteer.v3.learning import (
    AcceptedSample,
    ExclusionReason,
    RawRecorderSample,
    segment_episodes,
)


START = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _raw(
    minute: int,
    *,
    indoor: float = 21.0,
    outdoor: float = -5.0,
    target: float = 21.0,
    indoor_observed_minute: int | None = None,
    outdoor_observed_minute: int | None = None,
) -> RawRecorderSample:
    captured = START + timedelta(minutes=minute)
    indoor_at = START + timedelta(
        minutes=(minute if indoor_observed_minute is None else indoor_observed_minute)
    )
    outdoor_at = START + timedelta(
        minutes=(minute if outdoor_observed_minute is None else outdoor_observed_minute)
    )
    return RawRecorderSample(
        captured_at=captured,
        indoor_temperature_c=indoor,
        outdoor_temperature_c=outdoor,
        target_temperature_c=target,
        indoor_observed_at=indoor_at,
        outdoor_observed_at=outdoor_at,
    )


def _reasons(samples: list[RawRecorderSample]) -> tuple[ExclusionReason, ...]:
    batch = segment_episodes(samples)
    assert len(batch.excluded) == 1
    return batch.excluded[0].reasons


def test_episode_segmentation_is_deterministic() -> None:
    samples = [
        _raw(0),
        _raw(5, indoor=20.95),
        _raw(10, indoor=20.9, target=22.0),
        _raw(15, indoor=20.85, target=22.0),
        _raw(45, indoor=20.8, target=22.0),
        _raw(50, indoor=20.75, target=22.0),
    ]

    first = segment_episodes(samples)
    second = segment_episodes(samples)

    assert first == second
    assert [len(episode.samples) for episode in first.episodes] == [2, 1, 1]
    assert [item.reasons for item in first.excluded] == [
        (ExclusionReason.MANUAL_TARGET_CHANGE,),
        (ExclusionReason.EXCESSIVE_GAP,),
    ]


def test_duplicate_and_non_monotonic_capture_times_are_excluded() -> None:
    duplicate = [_raw(0), _raw(0)]
    backwards = [_raw(5), _raw(4)]

    assert ExclusionReason.DUPLICATE_TIME in _reasons(duplicate)
    assert ExclusionReason.NON_MONOTONIC_TIME in _reasons(backwards)


def test_duplicate_critical_source_timestamp_is_excluded() -> None:
    samples = [
        _raw(0),
        _raw(5, indoor_observed_minute=0, outdoor_observed_minute=5),
    ]

    assert ExclusionReason.DUPLICATE_SOURCE_TIME in _reasons(samples)


def test_non_monotonic_critical_source_timestamp_is_excluded() -> None:
    samples = [
        _raw(5),
        _raw(6, indoor_observed_minute=4, outdoor_observed_minute=6),
    ]

    assert ExclusionReason.NON_MONOTONIC_SOURCE_TIME in _reasons(samples)


def test_gap_target_change_window_opening_and_implausible_rate_are_excluded() -> None:
    scenarios = (
        (
            [_raw(0), _raw(30)],
            ExclusionReason.EXCESSIVE_GAP,
        ),
        (
            [_raw(0), _raw(5, target=22.0)],
            ExclusionReason.MANUAL_TARGET_CHANGE,
        ),
        (
            [_raw(0, indoor=21.0), _raw(10, indoor=20.7)],
            ExclusionReason.WINDOW_OPENING_SUSPECTED,
        ),
        (
            [_raw(0, indoor=21.0), _raw(10, indoor=19.0)],
            ExclusionReason.IMPLAUSIBLE_INDOOR_RATE,
        ),
    )

    for samples, expected in scenarios:
        assert expected in _reasons(samples)


def test_no_clean_episode_crosses_any_contaminated_sample() -> None:
    contaminants = (
        _raw(5, target=22.0),
        _raw(5, indoor=20.7),
        _raw(30),
        _raw(5, indoor_observed_minute=0),
    )

    for contaminated in contaminants:
        later_minute = int((contaminated.captured_at - START).total_seconds() / 60) + 5
        later_target = contaminated.target_temperature_c
        batch = segment_episodes(
            [
                _raw(0),
                contaminated,
                _raw(later_minute, target=later_target),
            ]
        )
        assert len(batch.excluded) >= 1
        assert all(
            contaminated.captured_at
            not in {sample.captured_at for sample in episode.samples}
            for episode in batch.episodes
        )
        assert all(len(episode.samples) == 1 for episode in batch.episodes)


def test_learning_types_expose_observations_but_no_control_authority() -> None:
    public_names = set(learning.__all__)
    forbidden_public = {
        "ControlDecision",
        "ControlEngine",
        "SupervisedOutput",
        "supervise_output",
        "apply_physical",
    }
    accepted_fields = {field.name for field in fields(AcceptedSample)}

    assert public_names.isdisjoint(forbidden_public)
    assert "heating_request" not in accepted_fields
    assert "curtailment" not in accepted_fields
    assert all(not name.startswith("async_") for name in public_names)
    assert all(
        getattr(learning, name).__module__.startswith(
            "custom_components.pumpsteer.v3.learning"
        )
        for name in public_names
    )
