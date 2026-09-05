"""Restart-equivalence scenarios for the persisted learning boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.pumpsteer.v3.learning.checkpoint import (
    LEARNING_CHECKPOINT_SCHEMA_VERSION,
    LEARNING_PIPELINE_VERSION,
    LearningCheckpoint,
    TargetEpoch,
)
from custom_components.pumpsteer.v3.learning.checkpoint_codec import (
    decode_learning_checkpoint,
    encode_learning_checkpoint,
)
from custom_components.pumpsteer.v3.learning.episodes import segment_episodes
from custom_components.pumpsteer.v3.learning.models import RawRecorderSample
from custom_components.pumpsteer.v3.learning.quality import ExclusionReason

START = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def sample(minute: int, *, indoor: float = 21.0) -> RawRecorderSample:
    captured = START + timedelta(minutes=minute)
    return RawRecorderSample(
        captured_at=captured,
        indoor_temperature_c=indoor,
        outdoor_temperature_c=-5.0,
        target_temperature_c=21.0,
        indoor_observed_at=captured,
        outdoor_observed_at=captured,
    )


def restore_boundary(boundary, *, cursor_minute: int):
    checkpoint = LearningCheckpoint(
        schema_version=LEARNING_CHECKPOINT_SCHEMA_VERSION,
        pipeline_version=LEARNING_PIPELINE_VERSION,
        entry_id="entry",
        saved_at=START + timedelta(minutes=cursor_minute),
        indoor_entity_id="sensor.indoor",
        outdoor_entity_id="sensor.outdoor",
        cursor_at=START + timedelta(minutes=cursor_minute),
        target_timeline=(TargetEpoch(START, 21.0),),
        boundary=boundary,
    )
    encoded = encode_learning_checkpoint(checkpoint)
    restored = decode_learning_checkpoint(
        encoded,
        expected_entry_id="entry",
        expected_indoor_entity_id="sensor.indoor",
        expected_outdoor_entity_id="sensor.outdoor",
        not_after=START + timedelta(minutes=cursor_minute),
    )
    return restored.boundary


def test_restart_preserves_one_episode_across_batch_boundary() -> None:
    samples = (
        sample(0),
        sample(5, indoor=20.95),
        sample(10, indoor=20.9),
        sample(15, indoor=20.85),
    )
    uninterrupted = segment_episodes(samples)
    before_restart = segment_episodes(samples[:2])
    boundary = restore_boundary(before_restart.boundary_after, cursor_minute=6)
    after_restart = segment_episodes(samples[2:], boundary=boundary)

    assert uninterrupted.excluded == after_restart.excluded == ()
    assert after_restart.first_episode_continues is True
    assert after_restart.new_episode_count == 0
    assert after_restart.boundary_after.open_episode_started_at == START
    assert after_restart.boundary_after.open_episode_sample_count == 4


def test_restart_keeps_rate_check_from_the_previous_batch() -> None:
    first = segment_episodes((sample(0),))
    boundary = restore_boundary(first.boundary_after, cursor_minute=1)

    second = segment_episodes((sample(5, indoor=19.0),), boundary=boundary)

    assert len(second.excluded) == 1
    assert ExclusionReason.IMPLAUSIBLE_INDOOR_RATE in second.excluded[0].reasons
    assert second.boundary_after.previous_accepted is None
    assert second.boundary_after.open_episode_sample_count == 0


def test_excluded_tail_does_not_reopen_episode_after_restart() -> None:
    first = segment_episodes((sample(0), sample(5, indoor=19.0)))
    boundary = restore_boundary(first.boundary_after, cursor_minute=6)

    second = segment_episodes((sample(10, indoor=19.0),), boundary=boundary)

    assert second.first_episode_continues is False
    assert second.new_episode_count == 1
    assert second.boundary_after.open_episode_sample_count == 1
