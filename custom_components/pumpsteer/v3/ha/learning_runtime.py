"""Transient observation-only learning runtime for PumpSteer V3."""

from __future__ import annotations

import asyncio
import logging
import math
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from ..enums import LearningStage
from ..learning.episodes import segment_episodes
from ..learning.models import RawRecorderSample
from .recorder import DEFAULT_MAX_SAMPLES, HARD_MAX_SAMPLES, MAX_LOOKBACK

_MAX_ERROR_LENGTH = 240
_MIN_TARGET_TEMPERATURE = 5.0
_MAX_TARGET_TEMPERATURE = 35.0

_LOGGER = logging.getLogger(__name__)


class LearningRuntimeStatus(StrEnum):
    """Transient status of the observation-only collection boundary."""

    WARMING_UP = "warming_up"
    RUNNING = "running"
    READY = "ready"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class LearningRuntimeConfig:
    """Validated Recorder limits for one observation runtime."""

    indoor_entity: str
    outdoor_entity: str
    collection_interval: timedelta = timedelta(hours=6)
    recorder_settle_delay: timedelta = timedelta(minutes=2)
    maximum_window: timedelta = timedelta(hours=24)
    maximum_samples: int = DEFAULT_MAX_SAMPLES

    def __post_init__(self) -> None:
        for field_name in ("indoor_entity", "outdoor_entity"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty entity ID")
        if self.indoor_entity == self.outdoor_entity:
            raise ValueError("indoor and outdoor entities must be distinct")
        if not isinstance(self.collection_interval, timedelta):
            raise TypeError("collection_interval must be a timedelta")
        if self.collection_interval <= timedelta(0):
            raise ValueError("collection_interval must be positive")
        if not isinstance(self.recorder_settle_delay, timedelta):
            raise TypeError("recorder_settle_delay must be a timedelta")
        if self.recorder_settle_delay < timedelta(0):
            raise ValueError("recorder_settle_delay must be non-negative")
        if not isinstance(self.maximum_window, timedelta):
            raise TypeError("maximum_window must be a timedelta")
        if not timedelta(0) < self.maximum_window <= MAX_LOOKBACK:
            raise ValueError("maximum_window must be positive and at most 31 days")
        if isinstance(self.maximum_samples, bool) or not isinstance(
            self.maximum_samples, int
        ):
            raise TypeError("maximum_samples must be an integer")
        if not 1 <= self.maximum_samples <= HARD_MAX_SAMPLES:
            raise ValueError("maximum_samples is outside the supported range")


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    """Aggregate-only state from the latest standalone observation batch."""

    stage: LearningStage
    status: LearningRuntimeStatus
    target_epoch_started_at: datetime
    cursor_at: datetime
    attempted_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    raw_sample_count: int = 0
    accepted_sample_count: int = 0
    episode_count: int = 0
    excluded_sample_count: int = 0
    exclusion_counts: tuple[tuple[str, int], ...] = ()
    last_error: str | None = None

    def __post_init__(self) -> None:
        if self.stage is not LearningStage.OBSERVING:
            raise ValueError("observation runtime stage must remain observing")
        _utc(self.target_epoch_started_at, "target_epoch_started_at")
        _utc(self.cursor_at, "cursor_at")
        for field_name in ("attempted_at", "window_start", "window_end"):
            value = getattr(self, field_name)
            if value is not None:
                _utc(value, field_name)


class RecorderHistorySource(Protocol):
    """Read-only subset implemented by :class:`RecorderHistoryAdapter`."""

    async def async_load(
        self,
        *,
        start: datetime,
        end: datetime,
        indoor_entity: str,
        outdoor_entity: str,
        target_temperature: float,
        maximum_samples: int = DEFAULT_MAX_SAMPLES,
    ) -> tuple[RawRecorderSample, ...]:
        """Return canonical samples for one bounded UTC interval."""


class ObservationLearningRuntime:
    """Collect Recorder snapshots without model or control authority.

    Batches intentionally have no overlap or persistent deduplication. Recorder
    rows delayed beyond the settlement margin can therefore be missed, so these
    transient counts must never grant cumulative confidence or model authority.
    """

    def __init__(
        self,
        *,
        config: LearningRuntimeConfig,
        recorder: RecorderHistorySource,
        started_at: datetime,
        target_temperature: float,
    ) -> None:
        self._config = config
        self._recorder = recorder
        self._target_temperature = _target(target_temperature)
        started_at = _utc(started_at, "started_at")
        self._snapshot = _empty_snapshot(
            status=LearningRuntimeStatus.WARMING_UP,
            epoch=started_at,
        )
        self._lock = asyncio.Lock()
        self._generation = 0

    @property
    def config(self) -> LearningRuntimeConfig:
        """Return immutable Recorder collection configuration."""
        return self._config

    @property
    def snapshot(self) -> LearningSnapshot:
        """Return the latest aggregate-only runtime snapshot."""
        return self._snapshot

    async def async_collect(self, *, now_utc: datetime) -> LearningSnapshot:
        """Collect one bounded standalone batch and contain adapter failures."""
        now_utc = _utc(now_utc, "now_utc")
        async with self._lock:
            if self._snapshot.status is LearningRuntimeStatus.STOPPED:
                return self._snapshot

            start = self._snapshot.cursor_at
            if now_utc < start:
                raise ValueError("now_utc cannot precede the collection cursor")
            settled_end = now_utc - self._config.recorder_settle_delay
            if settled_end <= start:
                return self._snapshot
            end = min(settled_end, start + self._config.maximum_window)
            generation = self._generation
            previous = self._snapshot
            self._snapshot = replace(
                previous,
                status=LearningRuntimeStatus.RUNNING,
                attempted_at=now_utc,
                last_error=None,
            )

            try:
                samples = await self._recorder.async_load(
                    start=start,
                    end=end,
                    indoor_entity=self._config.indoor_entity,
                    outdoor_entity=self._config.outdoor_entity,
                    target_temperature=self._target_temperature,
                    maximum_samples=self._config.maximum_samples,
                )
                if generation != self._generation:
                    return self._snapshot

                bounded_samples = tuple(
                    sample for sample in samples if start <= sample.captured_at < end
                )
                batch = segment_episodes(bounded_samples)
                accepted_count = sum(len(episode.samples) for episode in batch.episodes)
                reason_counts = Counter(
                    reason.value
                    for excluded in batch.excluded
                    for reason in excluded.reasons
                )
            except asyncio.CancelledError:
                if generation == self._generation:
                    self._snapshot = previous
                raise
            except Exception as err:
                _LOGGER.warning(
                    "Observation learning collection failed",
                    exc_info=True,
                )
                if generation == self._generation:
                    self._snapshot = replace(
                        self._snapshot,
                        status=LearningRuntimeStatus.ERROR,
                        window_start=start,
                        window_end=end,
                        raw_sample_count=0,
                        accepted_sample_count=0,
                        episode_count=0,
                        excluded_sample_count=0,
                        exclusion_counts=(),
                        last_error=_safe_error(err),
                    )
                return self._snapshot

            self._snapshot = LearningSnapshot(
                stage=LearningStage.OBSERVING,
                status=(
                    LearningRuntimeStatus.READY
                    if accepted_count
                    else LearningRuntimeStatus.WARMING_UP
                ),
                target_epoch_started_at=previous.target_epoch_started_at,
                cursor_at=end,
                attempted_at=now_utc,
                window_start=start,
                window_end=end,
                raw_sample_count=len(bounded_samples),
                accepted_sample_count=accepted_count,
                episode_count=len(batch.episodes),
                excluded_sample_count=len(batch.excluded),
                exclusion_counts=tuple(sorted(reason_counts.items())),
                last_error=None,
            )
            return self._snapshot

    def begin_target_epoch(
        self,
        *,
        changed_at: datetime,
        target_temperature: float,
    ) -> None:
        """Discard batch context when the user target changes."""
        changed_at = _utc(changed_at, "changed_at")
        target = _target(target_temperature)
        if self._snapshot.status is LearningRuntimeStatus.STOPPED:
            raise RuntimeError("a stopped learning runtime cannot start a new epoch")
        if changed_at < self._snapshot.target_epoch_started_at:
            raise ValueError("changed_at cannot precede the current target epoch")
        self._generation += 1
        self._target_temperature = target
        self._snapshot = _empty_snapshot(
            status=LearningRuntimeStatus.WARMING_UP,
            epoch=changed_at,
        )

    def stop(self) -> None:
        """Permanently stop collection and invalidate any in-flight result."""
        if self._snapshot.status is LearningRuntimeStatus.STOPPED:
            return
        self._generation += 1
        self._snapshot = replace(
            self._snapshot,
            status=LearningRuntimeStatus.STOPPED,
        )


def _empty_snapshot(
    *, status: LearningRuntimeStatus, epoch: datetime
) -> LearningSnapshot:
    return LearningSnapshot(
        stage=LearningStage.OBSERVING,
        status=status,
        target_epoch_started_at=epoch,
        cursor_at=epoch,
    )


def _target(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError("target_temperature must be numeric") from err
    if not math.isfinite(result):
        raise ValueError("target_temperature must be finite")
    if not _MIN_TARGET_TEMPERATURE <= result <= _MAX_TARGET_TEMPERATURE:
        raise ValueError("target_temperature must be between 5 and 35 °C")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value


def _safe_error(error: Exception) -> str:
    return f"collection_failed:{type(error).__name__}"[:_MAX_ERROR_LENGTH]
