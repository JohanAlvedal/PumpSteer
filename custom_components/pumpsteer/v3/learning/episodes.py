"""Deterministic segmentation of screened observations into clean episodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import AcceptedSample, RawRecorderSample
from .quality import QualityPolicy, ScreenedSample, screen_sample


@dataclass(frozen=True, slots=True)
class LearningEpisode:
    """A contiguous sequence containing only accepted observations."""

    samples: tuple[AcceptedSample, ...]

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError("an episode must contain at least one sample")


@dataclass(frozen=True, slots=True)
class EpisodeBatch:
    """Clean episodes and excluded observations from one ingestion pass."""

    episodes: tuple[LearningEpisode, ...]
    excluded: tuple[ScreenedSample, ...]


def segment_episodes(
    samples: Iterable[RawRecorderSample],
    *,
    policy: QualityPolicy = QualityPolicy(),
) -> EpisodeBatch:
    """Screen samples in provided order and split at every exclusion."""
    episodes: list[LearningEpisode] = []
    excluded: list[ScreenedSample] = []
    current: list[AcceptedSample] = []
    previous_raw: RawRecorderSample | None = None
    previous_accepted: AcceptedSample | None = None

    def finish_episode() -> None:
        if current:
            episodes.append(LearningEpisode(samples=tuple(current)))
            current.clear()

    for raw in samples:
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
        else:
            current.append(screened.accepted)
            previous_accepted = screened.accepted
        previous_raw = raw

    finish_episode()
    return EpisodeBatch(episodes=tuple(episodes), excluded=tuple(excluded))
