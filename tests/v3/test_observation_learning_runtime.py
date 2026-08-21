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
    assert result.cursor_at == START + timedelta(minutes=30)
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
    with pytest.raises(ValueError, match="cursor"):
        asyncio.run(instance.async_collect(now_utc=START + timedelta(minutes=59)))


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
