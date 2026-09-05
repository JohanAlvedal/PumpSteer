"""Persistent observation-only learning runtime for PumpSteer V3."""

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
from ..learning.checkpoint import (
    LEARNING_CHECKPOINT_SCHEMA_VERSION,
    LEARNING_PIPELINE_VERSION,
    MAX_TARGET_EPOCHS,
    LearningCheckpoint,
    TargetEpoch,
)
from ..learning.episodes import EpisodeBoundary, segment_episodes
from ..learning.models import RawRecorderSample
from .recorder import DEFAULT_MAX_SAMPLES, HARD_MAX_SAMPLES, MAX_LOOKBACK

_MAX_ERROR_LENGTH = 240
_MIN_TARGET_TEMPERATURE = 5.0
_MAX_TARGET_TEMPERATURE = 35.0

_LOGGER = logging.getLogger(__name__)


class LearningRuntimeStatus(StrEnum):
    """Status of the observation-only collection boundary."""

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
    """Aggregate-only state from the latest observation batch."""

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


class LearningCheckpointStore(Protocol):
    """Minimal durable checkpoint writer used by the runtime."""

    async def async_save(self, checkpoint: LearningCheckpoint) -> None:
        """Persist and verify one complete checkpoint."""


class ObservationLearningRuntime:
    """Collect Recorder observations with durable ingestion continuity.

    Batches intentionally have no overlap. Rows delayed beyond the settlement
    margin can be missed, so this runtime still grants no cumulative confidence,
    model authority, controller authority, or physical output permission.
    """

    def __init__(
        self,
        *,
        config: LearningRuntimeConfig,
        recorder: RecorderHistorySource,
        started_at: datetime,
        target_temperature: float,
        entry_id: str = "transient",
        store: LearningCheckpointStore | None = None,
        restored_checkpoint: LearningCheckpoint | None = None,
    ) -> None:
        self._config = config
        self._recorder = recorder
        self._store = store
        self._entry_id = _non_empty(entry_id, "entry_id")
        target = _target(target_temperature)
        started_at = _utc(started_at, "started_at")
        self._lock = asyncio.Lock()
        self._generation = 0
        self._initialized = False

        if restored_checkpoint is None:
            self._checkpoint = _new_checkpoint(
                entry_id=self._entry_id,
                config=config,
                started_at=started_at,
                target=target,
            )
            self._needs_initial_save = store is not None
        else:
            _validate_restored_checkpoint(
                restored_checkpoint,
                entry_id=self._entry_id,
                config=config,
                started_at=started_at,
            )
            self._checkpoint = restored_checkpoint
            self._needs_initial_save = False
            if restored_checkpoint.target_timeline[-1].target_temperature_c != target:
                # The target may have changed while its epoch write failed. Its true
                # start is unknowable after restart, so skip ambiguous history rather
                # than mislabel it with either target.
                self._checkpoint = _new_checkpoint(
                    entry_id=self._entry_id,
                    config=config,
                    started_at=started_at,
                    target=target,
                )
                self._needs_initial_save = store is not None

        self._snapshot = _empty_snapshot(
            status=LearningRuntimeStatus.WARMING_UP,
            epoch=self._checkpoint.target_timeline[-1].started_at,
            cursor=self._checkpoint.cursor_at,
        )

    @property
    def config(self) -> LearningRuntimeConfig:
        """Return immutable Recorder collection configuration."""
        return self._config

    @property
    def snapshot(self) -> LearningSnapshot:
        """Return the latest aggregate-only runtime snapshot."""
        return self._snapshot

    @property
    def checkpoint(self) -> LearningCheckpoint:
        """Return the immutable committed ingestion checkpoint."""
        return self._checkpoint

    async def async_initialize(self) -> None:
        """Persist a fresh or target-reconciled checkpoint before collection."""
        async with self._lock:
            if self._initialized:
                return
            if self._snapshot.status is LearningRuntimeStatus.STOPPED:
                return
            await self._initialize_locked()

    async def async_collect(self, *, now_utc: datetime) -> LearningSnapshot:
        """Collect and atomically commit one bounded observation batch."""
        now_utc = _utc(now_utc, "now_utc")
        async with self._lock:
            if self._snapshot.status is LearningRuntimeStatus.STOPPED:
                return self._snapshot
            if not self._initialized:
                await self._initialize_locked()
            if self._snapshot.status is LearningRuntimeStatus.STOPPED:
                return self._snapshot

            checkpoint = self._checkpoint
            start = checkpoint.cursor_at
            if now_utc < start:
                self._snapshot = LearningSnapshot(
                    stage=LearningStage.OBSERVING,
                    status=LearningRuntimeStatus.ERROR,
                    target_epoch_started_at=checkpoint.target_timeline[-1].started_at,
                    cursor_at=start,
                    attempted_at=now_utc,
                    last_error="clock_regression",
                )
                return self._snapshot
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
                    target_temperature=checkpoint.target_timeline[
                        -1
                    ].target_temperature_c,
                    maximum_samples=self._config.maximum_samples,
                )
                if (
                    generation != self._generation
                    or self._snapshot.status is LearningRuntimeStatus.STOPPED
                ):
                    return self._snapshot
                bounded = tuple(
                    sample for sample in samples if start <= sample.captured_at < end
                )
                result = _screen_window(
                    bounded,
                    start=start,
                    end=end,
                    checkpoint=checkpoint,
                )
                candidate = LearningCheckpoint(
                    schema_version=LEARNING_CHECKPOINT_SCHEMA_VERSION,
                    pipeline_version=LEARNING_PIPELINE_VERSION,
                    entry_id=self._entry_id,
                    saved_at=now_utc,
                    indoor_entity_id=self._config.indoor_entity,
                    outdoor_entity_id=self._config.outdoor_entity,
                    cursor_at=end,
                    target_timeline=_prune_timeline(
                        checkpoint.target_timeline,
                        cursor=end,
                    ),
                    boundary=result.boundary,
                )
                await self._save(candidate)
                if generation != self._generation:
                    return self._snapshot
            except asyncio.CancelledError:
                if generation == self._generation:
                    self._snapshot = previous
                raise
            except Exception as err:
                _LOGGER.warning("Observation learning collection failed", exc_info=True)
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

            self._checkpoint = candidate
            self._snapshot = LearningSnapshot(
                stage=LearningStage.OBSERVING,
                status=(
                    LearningRuntimeStatus.READY
                    if result.accepted_count
                    else LearningRuntimeStatus.WARMING_UP
                ),
                target_epoch_started_at=candidate.target_timeline[-1].started_at,
                cursor_at=end,
                attempted_at=now_utc,
                window_start=start,
                window_end=end,
                raw_sample_count=len(bounded),
                accepted_sample_count=result.accepted_count,
                episode_count=result.new_episode_count,
                excluded_sample_count=result.excluded_count,
                exclusion_counts=tuple(sorted(result.reason_counts.items())),
                last_error=None,
            )
            return self._snapshot

    async def async_note_target_change(
        self,
        *,
        changed_at: datetime,
        target_temperature: float,
    ) -> None:
        """Durably append a target epoch before HA persists the new setting."""
        changed_at = _utc(changed_at, "changed_at")
        target = _target(target_temperature)
        async with self._lock:
            if self._snapshot.status is LearningRuntimeStatus.STOPPED:
                raise RuntimeError(
                    "a stopped learning runtime cannot start a new epoch"
                )
            if not self._initialized:
                await self._initialize_locked()
            if self._snapshot.status is LearningRuntimeStatus.STOPPED:
                return
            candidate = _with_target_epoch(
                self._checkpoint,
                changed_at=changed_at,
                target=target,
            )
            generation = self._generation
            await self._save(candidate)
            if (
                generation != self._generation
                or self._snapshot.status is LearningRuntimeStatus.STOPPED
            ):
                return
            self._generation += 1
            self._checkpoint = candidate
            self._snapshot = _empty_snapshot(
                status=LearningRuntimeStatus.WARMING_UP,
                epoch=candidate.target_timeline[-1].started_at,
                cursor=candidate.cursor_at,
            )

    def begin_target_epoch(
        self,
        *,
        changed_at: datetime,
        target_temperature: float,
    ) -> None:
        """Retain the legacy synchronous API only for non-persistent runtimes."""
        if self._store is not None:
            raise RuntimeError("persistent target changes must be awaited")
        changed_at = _utc(changed_at, "changed_at")
        target = _target(target_temperature)
        if self._snapshot.status is LearningRuntimeStatus.STOPPED:
            raise RuntimeError("a stopped learning runtime cannot start a new epoch")
        self._checkpoint = _with_target_epoch(
            self._checkpoint,
            changed_at=changed_at,
            target=target,
        )
        self._generation += 1
        self._snapshot = _empty_snapshot(
            status=LearningRuntimeStatus.WARMING_UP,
            epoch=changed_at,
            cursor=self._checkpoint.cursor_at,
        )

    def stop(self) -> None:
        """Permanently stop collection and invalidate any in-flight result."""
        if self._snapshot.status is LearningRuntimeStatus.STOPPED:
            return
        self._generation += 1
        self._snapshot = replace(self._snapshot, status=LearningRuntimeStatus.STOPPED)

    async def async_shutdown(self) -> None:
        """Stop and drain every collection or target-persistence operation."""
        self.stop()
        async with self._lock:
            pass

    async def _initialize_locked(self) -> None:
        if self._needs_initial_save:
            await self._save(self._checkpoint)
            self._needs_initial_save = False
        self._initialized = True

    async def _save(self, checkpoint: LearningCheckpoint) -> None:
        if self._store is not None:
            await self._store.async_save(checkpoint)


@dataclass(frozen=True, slots=True)
class _WindowResult:
    boundary: EpisodeBoundary
    accepted_count: int
    new_episode_count: int
    excluded_count: int
    reason_counts: Counter[str]


def _screen_window(
    samples: tuple[RawRecorderSample, ...],
    *,
    start: datetime,
    end: datetime,
    checkpoint: LearningCheckpoint,
) -> _WindowResult:
    if any(
        current.captured_at < previous.captured_at
        for previous, current in zip(samples, samples[1:], strict=False)
    ):
        raise ValueError("Recorder samples must be ordered by captured_at")
    boundary = checkpoint.boundary
    active = checkpoint.target_epoch_at(start)
    accepted_count = 0
    new_episode_count = 0
    excluded_count = 0
    reason_counts: Counter[str] = Counter()
    group: list[RawRecorderSample] = []

    def screen_group() -> None:
        nonlocal boundary, accepted_count, new_episode_count, excluded_count
        if not group:
            return
        batch = segment_episodes(group, boundary=boundary)
        boundary = batch.boundary_after
        accepted_count += sum(len(episode.samples) for episode in batch.episodes)
        new_episode_count += batch.new_episode_count
        excluded_count += len(batch.excluded)
        reason_counts.update(
            reason.value for excluded in batch.excluded for reason in excluded.reasons
        )
        group.clear()

    for sample in samples:
        sample_epoch = checkpoint.target_epoch_at(sample.captured_at)
        if sample_epoch.started_at != active.started_at:
            screen_group()
            boundary = EpisodeBoundary()
            active = sample_epoch
        group.append(replace(sample, target_temperature_c=active.target_temperature_c))
    screen_group()

    end_epoch = checkpoint.target_epoch_at(end)
    if end_epoch.started_at != active.started_at:
        boundary = EpisodeBoundary()
    return _WindowResult(
        boundary=boundary,
        accepted_count=accepted_count,
        new_episode_count=new_episode_count,
        excluded_count=excluded_count,
        reason_counts=reason_counts,
    )


def _new_checkpoint(
    *,
    entry_id: str,
    config: LearningRuntimeConfig,
    started_at: datetime,
    target: float,
) -> LearningCheckpoint:
    return LearningCheckpoint(
        schema_version=LEARNING_CHECKPOINT_SCHEMA_VERSION,
        pipeline_version=LEARNING_PIPELINE_VERSION,
        entry_id=entry_id,
        saved_at=started_at,
        indoor_entity_id=config.indoor_entity,
        outdoor_entity_id=config.outdoor_entity,
        cursor_at=started_at,
        target_timeline=(TargetEpoch(started_at, target),),
    )


def _with_target_epoch(
    checkpoint: LearningCheckpoint,
    *,
    changed_at: datetime,
    target: float,
) -> LearningCheckpoint:
    if changed_at < checkpoint.cursor_at:
        raise ValueError("changed_at cannot precede the collection cursor")
    if changed_at < checkpoint.saved_at:
        raise ValueError("changed_at cannot precede the last checkpoint save")
    timeline = checkpoint.target_timeline
    latest = timeline[-1]
    if changed_at < latest.started_at:
        raise ValueError("changed_at cannot precede the current target epoch")
    if changed_at == latest.started_at:
        timeline = (*timeline[:-1], TargetEpoch(changed_at, target))
    else:
        timeline = (*timeline, TargetEpoch(changed_at, target))
    timeline = _prune_timeline(timeline, cursor=checkpoint.cursor_at)
    boundary = (
        EpisodeBoundary() if changed_at <= checkpoint.cursor_at else checkpoint.boundary
    )
    return LearningCheckpoint(
        schema_version=checkpoint.schema_version,
        pipeline_version=checkpoint.pipeline_version,
        entry_id=checkpoint.entry_id,
        saved_at=changed_at,
        indoor_entity_id=checkpoint.indoor_entity_id,
        outdoor_entity_id=checkpoint.outdoor_entity_id,
        cursor_at=checkpoint.cursor_at,
        target_timeline=timeline,
        boundary=boundary,
    )


def _prune_timeline(
    timeline: tuple[TargetEpoch, ...], *, cursor: datetime
) -> tuple[TargetEpoch, ...]:
    active_index = 0
    for index, epoch in enumerate(timeline):
        if epoch.started_at > cursor:
            break
        active_index = index
    retained = timeline[active_index:]
    if len(retained) > MAX_TARGET_EPOCHS:
        raise ValueError("too many pending target epochs before Recorder catches up")
    return retained


def _validate_restored_checkpoint(
    checkpoint: LearningCheckpoint,
    *,
    entry_id: str,
    config: LearningRuntimeConfig,
    started_at: datetime,
) -> None:
    if not isinstance(checkpoint, LearningCheckpoint):
        raise TypeError("restored_checkpoint must be a LearningCheckpoint")
    if checkpoint.entry_id != entry_id:
        raise ValueError("restored checkpoint entry does not match")
    if checkpoint.indoor_entity_id != config.indoor_entity:
        raise ValueError("restored checkpoint indoor entity does not match")
    if checkpoint.outdoor_entity_id != config.outdoor_entity:
        raise ValueError("restored checkpoint outdoor entity does not match")
    if started_at < checkpoint.saved_at:
        raise ValueError("started_at cannot precede the restored checkpoint")


def _empty_snapshot(
    *, status: LearningRuntimeStatus, epoch: datetime, cursor: datetime
) -> LearningSnapshot:
    return LearningSnapshot(
        stage=LearningStage.OBSERVING,
        status=status,
        target_epoch_started_at=epoch,
        cursor_at=cursor,
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


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value


def _safe_error(error: Exception) -> str:
    return f"collection_failed:{type(error).__name__}"[:_MAX_ERROR_LENGTH]
