"""Focused tests for the Home Assistant observation checkpoint store."""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar

import pytest

from custom_components.pumpsteer.v3.ha import learning_store as module

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeStore:
    """Controllable Store replacement with constructor call capture."""

    instances: ClassVar[list[FakeStore]] = []

    def __init__(self, hass, version, key, private=False, **kwargs) -> None:
        self.hass = hass
        self.version = version
        self.key = key
        self.private = private
        self.kwargs = kwargs
        self.value = None
        self.saved: list[object] = []
        self.readback = None
        self.fail_save: Exception | None = None
        type(self).instances.append(self)

    async def async_load(self):
        return self.value if self.readback is None else self.readback

    async def async_save(self, data) -> None:
        if self.fail_save is not None:
            raise self.fail_save
        self.saved.append(data)
        self.value = data


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    FakeStore.instances.clear()
    monkeypatch.setattr(module, "Store", FakeStore)


def create(entry_id: str = "entry-one") -> module.HomeAssistantLearningStore:
    return module.HomeAssistantLearningStore(SimpleNamespace(), entry_id)


def test_constructor_uses_private_atomic_versioned_per_entry_store() -> None:
    create("abc123")

    store = FakeStore.instances[0]
    assert store.version == 1
    assert store.key == "pumpsteer.v3.observation_learning.abc123"
    assert store.private is True
    assert store.kwargs == {
        "atomic_writes": True,
        "serialize_in_event_loop": True,
    }


def test_entries_use_distinct_storage_keys() -> None:
    create("first")
    create("second")

    assert [store.key for store in FakeStore.instances] == [
        "pumpsteer.v3.observation_learning.first",
        "pumpsteer.v3.observation_learning.second",
    ]


def test_empty_store_returns_none_without_decoding(monkeypatch) -> None:
    def unexpected_decode(*args, **kwargs):
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(module, "decode_learning_checkpoint", unexpected_decode)

    assert (
        asyncio.run(
            create().async_load(
                expected_entry_id="entry-one",
                expected_indoor_entity="sensor.indoor",
                expected_outdoor_entity="sensor.outdoor",
                not_after=NOW,
            )
        )
        is None
    )


def test_load_delegates_all_identity_and_time_validation(monkeypatch) -> None:
    adapter = create()
    encoded = {"schema_version": 1}
    expected = object()
    FakeStore.instances[0].value = encoded
    calls = []

    def decode(data, **kwargs):
        calls.append((data, kwargs))
        return expected

    monkeypatch.setattr(module, "decode_learning_checkpoint", decode)

    result = asyncio.run(
        adapter.async_load(
            expected_entry_id="entry-one",
            expected_indoor_entity="sensor.indoor",
            expected_outdoor_entity="sensor.outdoor",
            not_after=NOW,
        )
    )

    assert result is expected
    assert calls == [
        (
            encoded,
            {
                "expected_entry_id": "entry-one",
                "expected_indoor_entity_id": "sensor.indoor",
                "expected_outdoor_entity_id": "sensor.outdoor",
                "not_after": NOW,
            },
        )
    ]


def test_save_awaits_store_and_accepts_exact_readback(monkeypatch) -> None:
    adapter = create()
    checkpoint = object()
    encoded = {"schema_version": 1, "cursor_at": "2026-01-15T12:00:00Z"}
    monkeypatch.setattr(
        module,
        "encode_learning_checkpoint",
        lambda value: encoded if value is checkpoint else None,
    )

    asyncio.run(adapter.async_save(checkpoint))

    assert FakeStore.instances[0].saved == [encoded]


def test_save_rejects_mismatched_readback_with_stable_error(monkeypatch) -> None:
    adapter = create()
    checkpoint = object()
    encoded = {"schema_version": 1}
    store = FakeStore.instances[0]
    store.readback = {"schema_version": 1, "unexpected": True}
    monkeypatch.setattr(module, "encode_learning_checkpoint", lambda _value: encoded)

    with pytest.raises(
        module.LearningStoreWriteError,
        match="^learning checkpoint write verification failed$",
    ):
        asyncio.run(adapter.async_save(checkpoint))


def test_save_wraps_store_failure_without_exposing_details(monkeypatch) -> None:
    adapter = create()
    FakeStore.instances[0].fail_save = RuntimeError("secret storage path")
    monkeypatch.setattr(
        module,
        "encode_learning_checkpoint",
        lambda _value: {"schema_version": 1},
    )

    with pytest.raises(
        module.LearningStoreWriteError,
        match="^learning checkpoint write verification failed$",
    ) as raised:
        asyncio.run(adapter.async_save(object()))

    assert "secret" not in str(raised.value)


def test_cancelled_save_drains_started_atomic_write(monkeypatch) -> None:
    async def scenario() -> None:
        adapter = create()
        store = FakeStore.instances[0]
        encoded = {"schema_version": 1}
        entered = asyncio.Event()
        release = asyncio.Event()
        completed = asyncio.Event()

        async def blocking_save(data) -> None:
            entered.set()
            await release.wait()
            store.value = data
            completed.set()

        store.async_save = blocking_save
        monkeypatch.setattr(
            module,
            "encode_learning_checkpoint",
            lambda _value: encoded,
        )
        task = asyncio.create_task(adapter.async_save(object()))
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed.is_set()

    asyncio.run(scenario())


def test_adapter_has_no_delayed_save_remove_or_control_authority() -> None:
    source = inspect.getsource(module.HomeAssistantLearningStore)

    assert "async_delay_save" not in source
    assert "async_remove" not in source
    assert "apply_physical" not in source
    assert not hasattr(module.HomeAssistantLearningStore, "remove")
    assert not hasattr(module.HomeAssistantLearningStore, "publish")
    assert not hasattr(module.HomeAssistantLearningStore, "apply")


@pytest.mark.parametrize("entry_id", ["", "   ", None])
def test_invalid_entry_id_is_rejected(entry_id) -> None:
    with pytest.raises(ValueError, match="entry_id"):
        create(entry_id)
