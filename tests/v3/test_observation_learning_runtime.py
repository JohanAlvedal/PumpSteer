"""Tests for the transient observation-only learning runtime."""

from __future__ import annotations

import asyncio
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.components import recorder as recorder_component


if not hasattr(recorder_component, "get_instance"):
    recorder_component.get_instance = lambda _hass: None

from custom_components.pumpsteer.v3.enums import LearningStage
from custom_components.pumpsteer.v3.ha.learning_runtime import (
    LearningRuntimeConfig,
    LearningRuntimeStatus,
    ObservationLearningRuntime,
)
from custom_components.pumpsteer.v3.learning.models import RawRecorderSample


START = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def sample(minute: int, *, indoor: float = 20.0) -> RawRecorderSample:
    captured = START + timedelta(minutes=minute)
    return RawRecorderSample(
        captured_at=captured,
        indoor_temperature_c=indoor,
        outdoor_temperature_c=-5.0,
        target_temperature_c=21.0,
        indoor_observed_at=captured,
        outdoor_observed_at=captured,
    )


class FakeRecorder:
    def __init__(self, samples=()) -> None:
        self.samples = tuple(samples)
        self.calls: list[dict] = []

    async def async_load(self, **kwargs):
        self.calls.append(kwargs)
        return self.samples


class MemoryCheckpointStore:
    def __init__(self) -> None:
        self.saved = []
        self.fail = False

    async def async_save(self, checkpoint) -> None:
        if self.fail:
            raise RuntimeError("simulated durable write failure")
        self.saved.append(checkpoint)


def runtime(recorder, **config_overrides) -> ObservationLearningRuntime:
    return ObservationLearningRuntime(
        config=LearningRuntimeConfig(
            "sensor.indoor",
            "sensor.outdoor",
            **config_overrides,
        ),
        recorder=recorder,
        started_at=START,
        target_temperature=21.0,
    )


def test_success_uses_bounded_settled_window_and_aggregate_snapshot() -> None:
    recorder = FakeRecorder((sample(0), sample(10), sample(70)))
    instance = runtime(
        recorder,
        recorder_settle_delay=timedelta(minutes=2),
        maximum_window=timedelta(hours=1),
    )

    result = asyncio.run(instance.async_collect(now_utc=START + timedelta(hours=2)))

    assert recorder.calls == [
        {
            "start": START,
            "end": START + timedelta(hours=1),
            "indoor_entity": "sensor.indoor",
            "outdoor_entity": "sensor.outdoor",
            "target_temperature": 21.0,
            "maximum_samples": 10_000,
        }
    ]
    assert result.stage is LearningStage.OBSERVING
    assert result.status is LearningRuntimeStatus.READY
    assert result.cursor_at == START + timedelta(hours=1)
    assert result.raw_sample_count == 2
    assert result.accepted_sample_count == 2
    assert result.episode_count == 1
    assert result.excluded_sample_count == 0
    assert not (
        {"samples", "episodes", "batch"} & {item.name for item in fields(result)}
    )


def test_each_batch_replaces_counts_and_cursor_boundary_is_not_reprocessed() -> None:
    recorder = FakeRecorder((sample(0), sample(10)))
    instance = runtime(recorder, recorder_settle_delay=timedelta(0))
    first = asyncio.run(instance.async_collect(now_utc=START + timedelta(minutes=10)))
    recorder.samples = (sample(10), sample(20))

    second = asyncio.run(instance.async_collect(now_utc=START + timedelta(minutes=20)))

    assert first.raw_sample_count == 1
    assert second.raw_sample_count == 1
    assert second.accepted_sample_count == 1
    assert second.window_start == START + timedelta(minutes=10)
    assert second.window_end == START + timedelta(minutes=20)


def test_empty_success_advances_cursor_but_remains_warming_up() -> None:
    instance = runtime(FakeRecorder(), recorder_settle_delay=timedelta(0))

    result = asyncio.run(instance.async_collect(now_utc=START + timedelta(hours=1)))

    assert result.status is LearningRuntimeStatus.WARMING_UP
    assert result.cursor_at == START + timedelta(hours=1)
    assert result.raw_sample_count == 0


def test_adapter_error_is_contained_sanitized_and_does_not_advance_cursor() -> None:
    class FailingRecorder:
        async def async_load(self, **kwargs):
            del kwargs
            raise RuntimeError("secret/entity/path" + "x" * 400 + "\ntraceback")

    instance = runtime(FailingRecorder(), recorder_settle_delay=timedelta(0))

    result = asyncio.run(instance.async_collect(now_utc=START + timedelta(hours=1)))

    assert result.status is LearningRuntimeStatus.ERROR
    assert result.cursor_at == START
    assert result.last_error == "collection_failed:RuntimeError"
    assert len(result.last_error) <= 240
    assert "\n" not in result.last_error
    assert "secret" not in result.last_error


def test_cancelled_collection_propagates_without_state_advancement() -> None:
    class CancelledRecorder:
        async def async_load(self, **kwargs):
            del kwargs
            raise asyncio.CancelledError

    instance = runtime(CancelledRecorder(), recorder_settle_delay=timedelta(0))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(instance.async_collect(now_utc=START + timedelta(hours=1)))

    assert instance.snapshot.status is LearningRuntimeStatus.WARMING_UP
    assert instance.snapshot.cursor_at == START
    assert instance.snapshot.attempted_at is None


def test_same_now_queued_collection_becomes_noop() -> None:
    class BlockingRecorder(FakeRecorder):
        def __init__(self) -> None:
            super().__init__((sample(10),))
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def async_load(self, **kwargs):
            self.calls.append(kwargs)
            self.entered.set()
            await self.release.wait()
            return self.samples

    async def scenario():
        recorder = BlockingRecorder()
        instance = runtime(recorder, recorder_settle_delay=timedelta(0))
        first = asyncio.create_task(
            instance.async_collect(now_utc=START + timedelta(minutes=10))
        )
        await recorder.entered.wait()
        second = asyncio.create_task(
            instance.async_collect(now_utc=START + timedelta(minutes=10))
        )
        recorder.release.set()
        return instance, recorder, await first, await second

    instance, recorder, first, second = asyncio.run(scenario())

    assert len(recorder.calls) == 1
    assert first == second == instance.snapshot


def test_target_change_discards_late_result_and_starts_clean_epoch() -> None:
    class BlockingRecorder(FakeRecorder):
        def __init__(self) -> None:
            super().__init__((sample(10),))
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def async_load(self, **kwargs):
            self.calls.append(kwargs)
            self.entered.set()
            await self.release.wait()
            return self.samples

    async def scenario():
        recorder = BlockingRecorder()
        instance = runtime(recorder, recorder_settle_delay=timedelta(0))
        task = asyncio.create_task(
            instance.async_collect(now_utc=START + timedelta(hours=1))
        )
        await recorder.entered.wait()
        changed = START + timedelta(minutes=30)
        instance.begin_target_epoch(changed_at=changed, target_temperature=22.0)
        recorder.release.set()
        return instance, await task

    instance, result = asyncio.run(scenario())

    assert result == instance.snapshot
    assert result.status is LearningRuntimeStatus.WARMING_UP
    assert result.target_epoch_started_at == START + timedelta(minutes=30)
    # A target change must not skip unprocessed Recorder history.
    assert result.cursor_at == START
    assert result.raw_sample_count == 0


def test_stop_discards_late_result_and_is_permanent() -> None:
    class BlockingRecorder(FakeRecorder):
        def __init__(self) -> None:
            super().__init__((sample(10),))
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def async_load(self, **kwargs):
            self.calls.append(kwargs)
            self.entered.set()
            await self.release.wait()
            return self.samples

    async def scenario():
        recorder = BlockingRecorder()
        instance = runtime(recorder, recorder_settle_delay=timedelta(0))
        task = asyncio.create_task(
            instance.async_collect(now_utc=START + timedelta(hours=1))
        )
        await recorder.entered.wait()
        instance.stop()
        recorder.release.set()
        result = await task
        after = await instance.async_collect(now_utc=START + timedelta(hours=2))
        return instance, recorder, result, after

    instance, recorder, result, after = asyncio.run(scenario())

    assert result.status is LearningRuntimeStatus.STOPPED
    assert after == result == instance.snapshot
    assert len(recorder.calls) == 1


def test_config_and_time_validation_are_conservative() -> None:
    with pytest.raises(ValueError, match="distinct"):
        LearningRuntimeConfig("sensor.same", "sensor.same")
    with pytest.raises(ValueError, match="31 days"):
        LearningRuntimeConfig(
            "sensor.indoor",
            "sensor.outdoor",
            maximum_window=timedelta(days=32),
        )
    with pytest.raises(ValueError, match="collection_interval"):
        LearningRuntimeConfig(
            "sensor.indoor",
            "sensor.outdoor",
            collection_interval=timedelta(0),
        )
    with pytest.raises(ValueError, match="UTC"):
        asyncio.run(
            runtime(FakeRecorder()).async_collect(now_utc=START.replace(tzinfo=None))
        )
    instance = runtime(FakeRecorder(), recorder_settle_delay=timedelta(0))
    asyncio.run(instance.async_collect(now_utc=START + timedelta(hours=1)))
    result = asyncio.run(instance.async_collect(now_utc=START + timedelta(minutes=59)))
    assert result.status is LearningRuntimeStatus.ERROR
    assert result.cursor_at == START + timedelta(hours=1)
    assert result.last_error == "clock_regression"


def test_public_types_cannot_express_model_or_control_authority() -> None:
    names = {
        item.name
        for cls in (LearningRuntimeConfig, type(runtime(FakeRecorder()).snapshot))
        for item in fields(cls)
    }

    assert {"model", "confidence", "control", "apply_physical"}.isdisjoint(names)
    assert not hasattr(ObservationLearningRuntime, "write")
    assert not hasattr(ObservationLearningRuntime, "publish")
    assert not hasattr(ObservationLearningRuntime, "apply")


def test_checkpoint_write_failure_never_advances_committed_cursor() -> None:
    store = MemoryCheckpointStore()
    instance = ObservationLearningRuntime(
        config=LearningRuntimeConfig(
            "sensor.indoor",
            "sensor.outdoor",
            recorder_settle_delay=timedelta(0),
        ),
        recorder=FakeRecorder((sample(0),)),
        started_at=START,
        target_temperature=21.0,
        entry_id="entry-one",
        store=store,
    )

    asyncio.run(instance.async_initialize())
    store.fail = True
    result = asyncio.run(instance.async_collect(now_utc=START + timedelta(minutes=10)))

    assert result.status is LearningRuntimeStatus.ERROR
    assert result.cursor_at == START
    assert instance.checkpoint.cursor_at == START
    assert result.last_error == "collection_failed:RuntimeError"


def test_non_monotonic_recorder_batch_is_rejected_without_advancing() -> None:
    instance = runtime(
        FakeRecorder((sample(10), sample(5))),
        recorder_settle_delay=timedelta(0),
    )

    result = asyncio.run(instance.async_collect(now_utc=START + timedelta(minutes=20)))

    assert result.status is LearningRuntimeStatus.ERROR
    assert result.cursor_at == START
    assert result.last_error == "collection_failed:ValueError"


def test_restart_restores_episode_continuity_without_double_counting() -> None:
    store = MemoryCheckpointStore()
    first = ObservationLearningRuntime(
        config=LearningRuntimeConfig(
            "sensor.indoor",
            "sensor.outdoor",
            recorder_settle_delay=timedelta(0),
        ),
        recorder=FakeRecorder((sample(0),)),
        started_at=START,
        target_temperature=21.0,
        entry_id="entry-one",
        store=store,
    )
    asyncio.run(first.async_initialize())
    asyncio.run(first.async_collect(now_utc=START + timedelta(minutes=10)))

    second = ObservationLearningRuntime(
        config=first.config,
        recorder=FakeRecorder((sample(10),)),
        started_at=START + timedelta(minutes=20),
        target_temperature=21.0,
        entry_id="entry-one",
        store=store,
        restored_checkpoint=first.checkpoint,
    )
    asyncio.run(second.async_initialize())
    result = asyncio.run(second.async_collect(now_utc=START + timedelta(minutes=20)))

    assert result.accepted_sample_count == 1
    assert result.episode_count == 0
    assert second.checkpoint.boundary.open_episode_sample_count == 2


def test_restart_with_unrecorded_target_change_skips_ambiguous_history() -> None:
    store = MemoryCheckpointStore()
    first = ObservationLearningRuntime(
        config=LearningRuntimeConfig(
            "sensor.indoor",
            "sensor.outdoor",
            recorder_settle_delay=timedelta(0),
        ),
        recorder=FakeRecorder(),
        started_at=START,
        target_temperature=21.0,
        entry_id="entry-one",
        store=store,
    )
    asyncio.run(first.async_initialize())
    old_checkpoint = first.checkpoint

    restarted_at = START + timedelta(hours=2)
    recorder = FakeRecorder((sample(60),))
    restarted = ObservationLearningRuntime(
        config=first.config,
        recorder=recorder,
        started_at=restarted_at,
        target_temperature=22.0,
        entry_id="entry-one",
        store=store,
        restored_checkpoint=old_checkpoint,
    )
    asyncio.run(restarted.async_initialize())
    result = asyncio.run(
        restarted.async_collect(now_utc=restarted_at + timedelta(minutes=10))
    )

    assert recorder.calls[0]["start"] == restarted_at
    assert result.raw_sample_count == 0
    assert restarted.checkpoint.target_timeline[0].started_at == restarted_at
    assert restarted.checkpoint.target_timeline[0].target_temperature_c == 22.0


def test_shutdown_drains_target_write_without_reviving_old_runtime() -> None:
    async def scenario() -> tuple[ObservationLearningRuntime, MemoryCheckpointStore]:
        store = MemoryCheckpointStore()
        instance = ObservationLearningRuntime(
            config=LearningRuntimeConfig("sensor.indoor", "sensor.outdoor"),
            recorder=FakeRecorder(),
            started_at=START,
            target_temperature=21.0,
            entry_id="entry-one",
            store=store,
        )
        await instance.async_initialize()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocking_save(checkpoint) -> None:
            entered.set()
            await release.wait()
            store.saved.append(checkpoint)

        store.async_save = blocking_save
        target_task = asyncio.create_task(
            instance.async_note_target_change(
                changed_at=START + timedelta(minutes=10),
                target_temperature=22.0,
            )
        )
        await entered.wait()
        shutdown_task = asyncio.create_task(instance.async_shutdown())
        await asyncio.sleep(0)
        assert instance.snapshot.status is LearningRuntimeStatus.STOPPED
        assert not shutdown_task.done()

        release.set()
        await target_task
        await shutdown_task
        return instance, store

    instance, store = asyncio.run(scenario())

    assert instance.snapshot.status is LearningRuntimeStatus.STOPPED
    assert instance.checkpoint.target_timeline[-1].target_temperature_c == 21.0
    assert store.saved[-1].target_timeline[-1].target_temperature_c == 22.0


def test_historical_samples_use_the_target_epoch_active_at_capture_time() -> None:
    store = MemoryCheckpointStore()
    recorder = FakeRecorder((sample(10), sample(20), sample(40), sample(50)))
    instance = ObservationLearningRuntime(
        config=LearningRuntimeConfig(
            "sensor.indoor",
            "sensor.outdoor",
            recorder_settle_delay=timedelta(0),
        ),
        recorder=recorder,
        started_at=START,
        target_temperature=21.0,
        entry_id="entry-one",
        store=store,
    )

    asyncio.run(instance.async_initialize())
    asyncio.run(
        instance.async_note_target_change(
            changed_at=START + timedelta(minutes=30),
            target_temperature=22.0,
        )
    )
    result = asyncio.run(instance.async_collect(now_utc=START + timedelta(hours=1)))

    assert result.accepted_sample_count == 4
    assert result.episode_count == 2
    assert instance.checkpoint.target_timeline == (
        instance.checkpoint.target_timeline[0],
    )
    assert instance.checkpoint.target_timeline[0].target_temperature_c == 22.0
    assert instance.checkpoint.boundary.previous_accepted.target_temperature_c == 22.0
