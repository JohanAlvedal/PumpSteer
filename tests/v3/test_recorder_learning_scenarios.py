"""End-to-end Recorder merge and learning-quality scenarios."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from homeassistant.components import recorder as recorder_component


if not hasattr(recorder_component, "get_instance"):
    recorder_component.get_instance = lambda _hass: None

from custom_components.pumpsteer.v3.ha.recorder import merge_histories
from custom_components.pumpsteer.v3.learning import (
    ExclusionReason,
    RawRecorderSample,
    segment_episodes,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
INDOOR = "sensor.indoor"
OUTDOOR = "sensor.outdoor"


def _state(value, minute: int):
    observed = NOW + timedelta(minutes=minute)
    return SimpleNamespace(
        state=value,
        last_changed=observed,
        last_updated=observed,
        last_reported=observed,
        attributes={"unit_of_measurement": "°C"},
    )


def _merge(indoor, outdoor):
    return merge_histories(
        {INDOOR: indoor, OUTDOOR: outdoor},
        indoor_entity=INDOOR,
        outdoor_entity=OUTDOOR,
        target_temperature=21.0,
    )


def _sample(
    captured_minute: int,
    indoor_observed_minute: int,
    outdoor_observed_minute: int,
) -> RawRecorderSample:
    return RawRecorderSample(
        captured_at=NOW + timedelta(minutes=captured_minute),
        indoor_temperature_c=20.0,
        outdoor_temperature_c=-5.0,
        target_temperature_c=21.0,
        indoor_observed_at=NOW + timedelta(minutes=indoor_observed_minute),
        outdoor_observed_at=NOW + timedelta(minutes=outdoor_observed_minute),
    )


def test_alternating_source_updates_form_one_clean_episode() -> None:
    samples = _merge(
        [_state("20.0", 0), _state("20.1", 10)],
        [_state("-5.0", 0), _state("-4.9", 5), _state("-4.8", 15)],
    )

    batch = segment_episodes(samples)

    assert batch.excluded == ()
    assert len(batch.episodes) == 1
    assert [sample.captured_at for sample in batch.episodes[0].samples] == [
        sample.captured_at for sample in samples
    ]
    assert [sample.indoor_observed_at for sample in batch.episodes[0].samples] == [
        sample.indoor_observed_at for sample in samples
    ]


def test_both_unchanged_sources_are_excluded_as_no_information() -> None:
    samples = (
        _sample(0, 0, 0),
        _sample(5, 0, 0),
    )

    batch = segment_episodes(samples)

    assert len(batch.excluded) == 1
    assert ExclusionReason.NO_NEW_CRITICAL_OBSERVATION in (batch.excluded[0].reasons)


def test_backward_critical_source_timestamp_is_excluded() -> None:
    samples = (
        _sample(5, 5, 5),
        _sample(6, 4, 6),
    )

    batch = segment_episodes(samples)

    assert len(batch.excluded) == 1
    assert ExclusionReason.SOURCE_TIME_REGRESSION in batch.excluded[0].reasons


def test_stale_carried_forward_source_breaks_episode() -> None:
    samples = _merge(
        [_state("20.0", 0)],
        [_state("-5.0", 0), _state("-4.5", 15)],
    )

    batch = segment_episodes(samples)

    assert len(batch.episodes) == 1
    assert len(batch.episodes[0].samples) == 1
    assert len(batch.excluded) == 1
    assert ExclusionReason.STALE_SOURCE in batch.excluded[0].reasons


def test_bad_recorder_values_become_exclusions_instead_of_exceptions() -> None:
    for bad_value in ("unknown", "unavailable", "not-a-number"):
        samples = _merge(
            [_state(bad_value, 0)],
            [_state("-5.0", 0)],
        )
        batch = segment_episodes(samples)

        assert batch.episodes == ()
        assert len(batch.excluded) == 1
        assert ExclusionReason.MISSING_INDOOR in batch.excluded[0].reasons


def test_recorder_learning_replay_is_deterministic_and_observational_only() -> None:
    histories = (
        [_state("20.0", 0), _state("20.1", 10)],
        [_state("-5.0", 0), _state("-4.9", 5)],
    )

    first = segment_episodes(_merge(*histories))
    second = segment_episodes(_merge(*histories))

    assert first == second
    assert all(
        "apply_physical" not in sample.__dataclass_fields__
        for episode in first.episodes
        for sample in episode.samples
    )
