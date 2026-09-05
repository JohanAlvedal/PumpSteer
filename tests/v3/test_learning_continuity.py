"""Stateful batch-continuity tests for observation-only learning."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3.learning import (
    AcceptedSample,
    EpisodeBoundary,
    ExclusionReason,
    RawRecorderSample,
    RawTimelineBoundary,
    segment_episodes,
)

START = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def sample(
    minute: int,
    *,
    indoor: float = 20.0,
    indoor_observed_minute: int | None = None,
    outdoor_observed_minute: int | None = None,
) -> RawRecorderSample:
    captured = START + timedelta(minutes=minute)
    return RawRecorderSample(
        captured_at=captured,
        indoor_temperature_c=indoor,
        outdoor_temperature_c=-5.0,
        target_temperature_c=21.0,
        indoor_observed_at=START
        + timedelta(
            minutes=(
                minute if indoor_observed_minute is None else indoor_observed_minute
            )
        ),
        outdoor_observed_at=START
        + timedelta(
            minutes=(
                minute if outdoor_observed_minute is None else outdoor_observed_minute
            )
        ),
    )


def test_clean_episode_continues_across_batch_without_new_episode() -> None:
    first = segment_episodes((sample(0), sample(5)))

    second = segment_episodes((sample(10),), boundary=first.boundary_after)

    assert second.first_episode_continues is True
    assert second.new_episode_count == 0
    assert [len(episode.samples) for episode in second.episodes] == [1]
    assert second.boundary_after.open_episode_started_at == START
    assert second.boundary_after.open_episode_sample_count == 3
    assert second.boundary_after.previous_accepted.captured_at == START + timedelta(
        minutes=10
    )


def test_gap_is_screened_against_previous_batch_and_closes_episode() -> None:
    first = segment_episodes((sample(0), sample(5)))

    second = segment_episodes((sample(30),), boundary=first.boundary_after)

    assert second.episodes == ()
    assert second.new_episode_count == 0
    assert second.first_episode_continues is False
    assert second.excluded[0].reasons == (ExclusionReason.EXCESSIVE_GAP,)
    assert second.boundary_after.previous_accepted is None
    assert second.boundary_after.open_episode_started_at is None
    assert second.boundary_after.open_episode_sample_count == 0
    assert second.boundary_after.previous_raw.captured_at == START + timedelta(
        minutes=30
    )


def test_source_regression_is_screened_using_compact_previous_raw() -> None:
    first = segment_episodes((sample(5),))

    second = segment_episodes(
        (
            sample(
                6,
                indoor_observed_minute=4,
                outdoor_observed_minute=6,
            ),
        ),
        boundary=first.boundary_after,
    )

    assert ExclusionReason.SOURCE_TIME_REGRESSION in second.excluded[0].reasons


def test_exclusion_then_acceptance_starts_one_new_episode() -> None:
    first = segment_episodes((sample(0),))

    second = segment_episodes(
        (sample(30), sample(35)),
        boundary=first.boundary_after,
    )

    assert second.first_episode_continues is False
    assert second.new_episode_count == 1
    assert [len(episode.samples) for episode in second.episodes] == [1]
    assert second.boundary_after.open_episode_started_at == START + timedelta(
        minutes=35
    )
    assert second.boundary_after.open_episode_sample_count == 1


def test_empty_batch_preserves_boundary_without_creating_fragment() -> None:
    boundary = segment_episodes((sample(0), sample(5))).boundary_after

    result = segment_episodes((), boundary=boundary)

    assert result.episodes == ()
    assert result.excluded == ()
    assert result.boundary_after == boundary
    assert result.new_episode_count == 0
    assert result.first_episode_continues is False


def test_default_boundary_preserves_standalone_segmentation_behavior() -> None:
    result = segment_episodes((sample(0), sample(5), sample(30), sample(35)))

    assert [len(episode.samples) for episode in result.episodes] == [2, 1]
    assert result.excluded[0].reasons == (ExclusionReason.EXCESSIVE_GAP,)
    assert result.new_episode_count == 2
    assert result.first_episode_continues is False


def test_raw_boundary_retains_only_timeline_fields() -> None:
    raw = sample(5, indoor=19.75)

    boundary = RawTimelineBoundary.from_sample(raw)

    assert {field.name for field in fields(boundary)} == {
        "captured_at",
        "indoor_observed_at",
        "outdoor_observed_at",
    }
    assert boundary.captured_at == raw.captured_at
    assert not hasattr(boundary, "indoor_temperature_c")
    assert not hasattr(boundary, "target_temperature_c")


def test_episode_boundary_rejects_inconsistent_open_state() -> None:
    raw = sample(5)
    accepted = AcceptedSample(
        captured_at=raw.captured_at,
        indoor_temperature_c=20.0,
        outdoor_temperature_c=-5.0,
        target_temperature_c=21.0,
        indoor_observed_at=raw.indoor_observed_at,
        outdoor_observed_at=raw.outdoor_observed_at,
    )
    timeline = RawTimelineBoundary.from_sample(raw)

    with pytest.raises(ValueError, match="requires previous_accepted"):
        EpisodeBoundary(open_episode_started_at=START)
    with pytest.raises(ValueError, match="must be zero"):
        EpisodeBoundary(open_episode_sample_count=1)
    with pytest.raises(ValueError, match="requires previous_raw"):
        EpisodeBoundary(
            previous_accepted=accepted,
            open_episode_started_at=START,
            open_episode_sample_count=1,
        )
    with pytest.raises(ValueError, match="cannot follow"):
        EpisodeBoundary(
            previous_raw=timeline,
            previous_accepted=accepted,
            open_episode_started_at=raw.captured_at + timedelta(seconds=1),
            open_episode_sample_count=1,
        )
    with pytest.raises(ValueError, match="must describe"):
        EpisodeBoundary(
            previous_raw=RawTimelineBoundary(
                captured_at=raw.captured_at - timedelta(minutes=1),
                indoor_observed_at=raw.indoor_observed_at,
                outdoor_observed_at=raw.outdoor_observed_at,
            ),
            previous_accepted=accepted,
            open_episode_started_at=START,
            open_episode_sample_count=1,
        )


def test_continuity_types_have_no_model_or_control_authority() -> None:
    names = {
        field.name
        for cls in (RawTimelineBoundary, EpisodeBoundary)
        for field in fields(cls)
    }

    assert {"model", "confidence", "control", "apply_physical"}.isdisjoint(names)
