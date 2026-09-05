"""Deterministic segmentation of screened observations into clean episodes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import AcceptedSample, RawRecorderSample, RawTimelineBoundary
from .quality import QualityPolicy, ScreenedSample, screen_sample


@dataclass(frozen=True, slots=True)
class LearningEpisode:
    """A contiguous sequence containing only accepted observations."""

    samples: tuple[AcceptedSample, ...]

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError("an episode must contain at least one sample")


@dataclass(frozen=True, slots=True)
class EpisodeBoundary:
    """Minimal validated continuity state carried between ingestion batches."""

    previous_raw: RawTimelineBoundary | None = None
    previous_accepted: AcceptedSample | None = None
    open_episode_started_at: datetime | None = None
    open_episode_sample_count: int = 0

    def __post_init__(self) -> None:
        if self.previous_raw is not None and not isinstance(
            self.previous_raw, RawTimelineBoundary
        ):
            raise TypeError("previous_raw must be a RawTimelineBoundary")
        if self.previous_accepted is not None and not isinstance(
            self.previous_accepted, AcceptedSample
        ):
            raise TypeError("previous_accepted must be an AcceptedSample")
        if isinstance(self.open_episode_sample_count, bool) or not isinstance(
            self.open_episode_sample_count, int
        ):
            raise TypeError("open_episode_sample_count must be an integer")

        if self.previous_accepted is None:
            if self.open_episode_started_at is not None:
                raise ValueError("open_episode_started_at requires previous_accepted")
            if self.open_episode_sample_count != 0:
                raise ValueError(
                    "open_episode_sample_count must be zero without previous_accepted"
                )
            return

        if self.previous_raw is None:
            raise ValueError("previous_accepted requires previous_raw")
        if self.open_episode_started_at is None:
            raise ValueError("previous_accepted requires open_episode_started_at")
        if self.open_episode_sample_count <= 0:
            raise ValueError(
                "open_episode_sample_count must be positive for an open episode"
            )
        started_at = _utc(self.open_episode_started_at, "open_episode_started_at")
        object.__setattr__(self, "open_episode_started_at", started_at)
        accepted = self.previous_accepted
        raw = self.previous_raw
        if started_at > accepted.captured_at:
            raise ValueError("open_episode_started_at cannot follow previous_accepted")
        if (
            raw.captured_at != accepted.captured_at
            or raw.indoor_observed_at != accepted.indoor_observed_at
            or raw.outdoor_observed_at != accepted.outdoor_observed_at
        ):
            raise ValueError("previous_raw must describe previous_accepted")


@dataclass(frozen=True, slots=True)
class EpisodeBatch:
    """Clean episodes and excluded observations from one ingestion pass."""

    episodes: tuple[LearningEpisode, ...]
    excluded: tuple[ScreenedSample, ...]
    boundary_after: EpisodeBoundary = EpisodeBoundary()
    new_episode_count: int = 0
    first_episode_continues: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.new_episode_count, bool) or not isinstance(
            self.new_episode_count, int
        ):
            raise TypeError("new_episode_count must be an integer")
        if self.new_episode_count < 0:
            raise ValueError("new_episode_count must be non-negative")
        if not isinstance(self.first_episode_continues, bool):
            raise TypeError("first_episode_continues must be a boolean")


def segment_episodes(
    samples: Iterable[RawRecorderSample],
    *,
    policy: QualityPolicy = QualityPolicy(),  # noqa: B008
    boundary: EpisodeBoundary = EpisodeBoundary(),  # noqa: B008
) -> EpisodeBatch:
    """Screen samples in order, preserving clean continuity between batches."""
    if not isinstance(boundary, EpisodeBoundary):
        raise TypeError("boundary must be an EpisodeBoundary")
    episodes: list[LearningEpisode] = []
    excluded: list[ScreenedSample] = []
    current: list[AcceptedSample] = []
    previous_raw = boundary.previous_raw
    previous_accepted = boundary.previous_accepted
    open_episode_started_at = boundary.open_episode_started_at
    open_episode_sample_count = boundary.open_episode_sample_count
    new_episode_count = 0
    first_episode_continues = False
    saw_sample = False

    def finish_episode() -> None:
        if current:
            episodes.append(LearningEpisode(samples=tuple(current)))
            current.clear()

    for raw in samples:
        if not isinstance(raw, RawRecorderSample):
            raise TypeError("samples must contain RawRecorderSample instances")
        screened = screen_sample(
            raw,
            policy=policy,
            previous_raw=previous_raw,
            previous_accepted=previous_accepted,
        )
        if screened.accepted is None:
            finish_episode()
            excluded.append(screened)
            previous_accepted = None
            open_episode_started_at = None
            open_episode_sample_count = 0
        else:
            if previous_accepted is None:
                new_episode_count += 1
                open_episode_started_at = screened.accepted.captured_at
                open_episode_sample_count = 0
            elif not saw_sample:
                first_episode_continues = True
            current.append(screened.accepted)
            previous_accepted = screened.accepted
            open_episode_sample_count += 1
        previous_raw = RawTimelineBoundary.from_sample(raw)
        saw_sample = True

    finish_episode()
    return EpisodeBatch(
        episodes=tuple(episodes),
        excluded=tuple(excluded),
        boundary_after=EpisodeBoundary(
            previous_raw=previous_raw,
            previous_accepted=previous_accepted,
            open_episode_started_at=open_episode_started_at,
            open_episode_sample_count=open_episode_sample_count,
        ),
        new_episode_count=new_episode_count,
        first_episode_continues=first_episode_continues,
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value
