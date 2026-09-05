"""Tests for the observation-only learning timer lifecycle."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer.v3.ha import learning_coordinator as module


NOW_LOCAL = datetime(
    2026,
    1,
    15,
    13,
    0,
    tzinfo=timezone(timedelta(hours=1)),
)


class FakeRuntime:
    def __init__(self) -> None:
        self.config = SimpleNamespace(collection_interval=timedelta(hours=6))
        self.calls: list[datetime] = []
        self.stops = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.shutdowns = 0
        self.stopped = False

    async def async_collect(self, *, now_utc: datetime) -> None:
        self.calls.append(now_utc)
        self.entered.set()
        await self.release.wait()

    def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        self.stops += 1

    async def async_shutdown(self) -> None:
        self.shutdowns += 1
        self.stop()


class FakeHass:
    def __init__(self) -> None:
        self.tasks: list[asyncio.Task] = []

    def async_create_task(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


def test_start_is_idempotent_and_does_not_query_immediately(monkeypatch) -> None:
    tracked = []
    cancels = []

    def track(hass, action, interval):
        tracked.append((hass, action, interval))
        return lambda: cancels.append(True)

    monkeypatch.setattr(module, "async_track_time_interval", track)
    runtime = FakeRuntime()
    hass = FakeHass()
    coordinator = module.ObservationLearningCoordinator(hass, runtime)

    coordinator.start()
    coordinator.start()

    assert tracked == [
        (hass, coordinator._interval_elapsed, timedelta(hours=6)),
    ]
    assert runtime.calls == []
    assert hass.tasks == []
    assert cancels == []


def test_timer_converts_to_utc_and_coalesces_overlapping_trigger(
    monkeypatch,
) -> None:
    callback_holder = {}
    monkeypatch.setattr(
        module,
        "async_track_time_interval",
        lambda _hass, action, _interval: (
            callback_holder.update(action=action) or (lambda: None)
        ),
    )

    async def scenario() -> None:
        runtime = FakeRuntime()
        hass = FakeHass()
        coordinator = module.ObservationLearningCoordinator(hass, runtime)
        coordinator.start()

        callback_holder["action"](NOW_LOCAL)
        await runtime.entered.wait()
        callback_holder["action"](NOW_LOCAL + timedelta(hours=6))

        assert runtime.calls == [
            datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        ]
        assert len(hass.tasks) == 1

        runtime.release.set()
        await hass.tasks[0]
        await asyncio.sleep(0)

        callback_holder["action"](NOW_LOCAL + timedelta(hours=12))
        await asyncio.sleep(0)
        assert len(hass.tasks) == 2
        runtime.release.set()
        await hass.tasks[1]

    asyncio.run(scenario())


def test_stop_is_idempotent_and_cancels_active_work(monkeypatch) -> None:
    cancelled = []
    callback_holder = {}

    def track(_hass, action, _interval):
        callback_holder["action"] = action
        return lambda: cancelled.append(True)

    monkeypatch.setattr(module, "async_track_time_interval", track)

    async def scenario() -> None:
        runtime = FakeRuntime()
        hass = FakeHass()
        coordinator = module.ObservationLearningCoordinator(hass, runtime)
        coordinator.start()
        callback_holder["action"](NOW_LOCAL)
        await runtime.entered.wait()

        coordinator.stop()
        coordinator.stop()
        await asyncio.sleep(0)

        assert cancelled == [True]
        assert runtime.stops == 1
        assert runtime.shutdowns == 0
        assert hass.tasks[0].cancelled()

        callback_holder["action"](NOW_LOCAL + timedelta(hours=6))
        assert len(hass.tasks) == 1

    asyncio.run(scenario())


def test_async_shutdown_drains_active_task(monkeypatch) -> None:
    callback_holder = {}
    monkeypatch.setattr(
        module,
        "async_track_time_interval",
        lambda _hass, action, _interval: (
            callback_holder.update(action=action) or (lambda: None)
        ),
    )

    async def scenario() -> None:
        runtime = FakeRuntime()
        hass = FakeHass()
        coordinator = module.ObservationLearningCoordinator(hass, runtime)
        coordinator.start()
        callback_holder["action"](NOW_LOCAL)
        await runtime.entered.wait()

        await coordinator.async_shutdown()

        assert hass.tasks[0].done()
        assert hass.tasks[0].cancelled()
        assert runtime.stops == 1
        assert runtime.shutdowns == 1

    asyncio.run(scenario())


def test_task_failure_is_consumed_and_future_interval_can_run(
    monkeypatch, caplog
) -> None:
    callback_holder = {}
    monkeypatch.setattr(
        module,
        "async_track_time_interval",
        lambda _hass, action, _interval: (
            callback_holder.update(action=action) or (lambda: None)
        ),
    )

    class FailingRuntime(FakeRuntime):
        async def async_collect(self, *, now_utc: datetime) -> None:
            self.calls.append(now_utc)
            raise RuntimeError("simulated failure")

    async def scenario() -> None:
        runtime = FailingRuntime()
        hass = FakeHass()
        coordinator = module.ObservationLearningCoordinator(hass, runtime)
        coordinator.start()

        callback_holder["action"](NOW_LOCAL)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        callback_holder["action"](NOW_LOCAL + timedelta(hours=6))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert len(hass.tasks) == 2
        assert len(runtime.calls) == 2

    asyncio.run(scenario())
    assert "Unexpected observation learning task failure" in caplog.text


def test_naive_timer_timestamp_is_rejected_without_creating_task(
    monkeypatch,
) -> None:
    callback_holder = {}
    monkeypatch.setattr(
        module,
        "async_track_time_interval",
        lambda _hass, action, _interval: (
            callback_holder.update(action=action) or (lambda: None)
        ),
    )
    runtime = FakeRuntime()
    hass = FakeHass()
    coordinator = module.ObservationLearningCoordinator(hass, runtime)
    coordinator.start()

    with pytest.raises(ValueError, match="timezone-aware"):
        callback_holder["action"](datetime(2026, 1, 15, 12, 0))

    assert hass.tasks == []
