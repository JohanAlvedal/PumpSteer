"""Tests for the optional Ohmigo Active/Bypass Relay Guard."""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import relay_guard

ENTRY_ID = "relay-guard-test"
RELAY_ENTITY = "switch.ohmigo_relay"
PUSH_ENTITY = "switch.pumpsteer_ohmigo_push"
GUARD_ENTITY = "switch.pumpsteer_ohmigo_relay_guard"


class _FakeStates:
    def __init__(self):
        self.values = {}

    def get(self, entity_id):
        value = self.values.get(entity_id)
        if value is None:
            return None
        if hasattr(value, "state"):
            return value
        return SimpleNamespace(state=value, attributes={})

    def set(self, entity_id, state):
        self.values[entity_id] = state


class _FakeServices:
    def __init__(self, states):
        self.states = states
        self.calls = []
        self.on_call = None

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))
        if self.on_call is not None:
            self.on_call(len(self.calls))


class _FakeBus:
    def __init__(self):
        self.listeners = []

    def async_listen_once(self, event_type, callback):
        item = [event_type, callback, False]
        self.listeners.append(item)

        def unsubscribe():
            item[2] = True

        return unsubscribe


class _FakeHass:
    def __init__(self):
        self.states = _FakeStates()
        self.services = _FakeServices(self.states)
        self.bus = _FakeBus()
        self.is_running = False

    def async_create_task(self, coro):
        return asyncio.create_task(coro)


class _FakeRegistry:
    def async_get_entity_id(self, domain, platform, unique_id):
        assert domain == "switch"
        assert platform == "pumpsteer"
        mapping = {
            f"{ENTRY_ID}_ohmigo_enabled": PUSH_ENTITY,
            f"{ENTRY_ID}_ohmigo_relay_guard": GUARD_ENTITY,
        }
        return mapping.get(unique_id)


@pytest.fixture
def guard_setup(monkeypatch):
    hass = _FakeHass()
    entry = SimpleNamespace(
        entry_id=ENTRY_ID,
        data={},
        options={"ohmigo_relay_entity": RELAY_ENTITY},
    )
    registry = _FakeRegistry()
    monkeypatch.setattr(relay_guard.er, "async_get", lambda hass_obj: registry)

    original_sleep = asyncio.sleep

    async def fast_sleep(_seconds):
        await original_sleep(0)

    monkeypatch.setattr(relay_guard.asyncio, "sleep", fast_sleep)

    hass.states.set(GUARD_ENTITY, "on")
    hass.states.set(PUSH_ENTITY, "on")
    hass.states.set(RELAY_ENTITY, "off")

    manager = relay_guard.OhmigoRelayGuard(hass, entry, RELAY_ENTITY)
    return hass, entry, manager


def _run(coro):
    return asyncio.run(coro)


def _turn_on_calls(hass):
    return [
        call
        for call in hass.services.calls
        if call[0] == "switch" and call[1] == "turn_on"
    ]


def test_no_relay_configured_creates_no_guard():
    hass = _FakeHass()
    entry = SimpleNamespace(entry_id=ENTRY_ID, data={}, options={})

    assert relay_guard.create_relay_guard(hass, entry) is None


@pytest.mark.parametrize(
    ("guard_state", "push_state", "relay_state", "expected_status"),
    [
        ("off", "on", "off", "disarmed"),
        ("on", "off", "off", "inhibited_by_push"),
        ("on", "on", "unknown", "relay_unavailable"),
        ("on", "on", "unavailable", "relay_unavailable"),
        ("on", "on", "on", "healthy"),
    ],
)
def test_fail_closed_gates_send_no_command(
    guard_setup,
    guard_state,
    push_state,
    relay_state,
    expected_status,
):
    hass, _, manager = guard_setup
    hass.states.set(GUARD_ENTITY, guard_state)
    hass.states.set(PUSH_ENTITY, push_state)
    hass.states.set(RELAY_ENTITY, relay_state)

    assert _run(manager.async_check("test")) == expected_status
    assert _turn_on_calls(hass) == []


def test_first_attempt_must_be_confirmed_by_relay_state(guard_setup):
    hass, _, manager = guard_setup

    def succeed_on_first(attempt):
        if attempt == 1:
            hass.states.set(RELAY_ENTITY, "on")

    hass.services.on_call = succeed_on_first

    assert _run(manager.async_check("relay_off")) == "healthy"
    assert len(_turn_on_calls(hass)) == 1
    assert manager.diagnostics["last_recovery"] is not None
    assert manager.diagnostics["recovery_attempts"] == 1


def test_retries_are_bounded_and_later_success_is_verified(guard_setup):
    hass, _, manager = guard_setup

    def succeed_on_third(attempt):
        if attempt == 3:
            hass.states.set(RELAY_ENTITY, "on")

    hass.services.on_call = succeed_on_third

    assert _run(manager.async_check("relay_off")) == "healthy"
    assert len(_turn_on_calls(hass)) == 3
    assert manager.diagnostics["recovery_attempts"] == 3


def test_three_failed_attempts_end_in_failed_state(guard_setup):
    hass, _, manager = guard_setup

    assert _run(manager.async_check("relay_off")) == "failed"
    assert len(_turn_on_calls(hass)) == 3
    assert manager.diagnostics["last_failure"] is not None


@pytest.mark.parametrize(
    ("changed_entity", "new_state", "expected_status"),
    [
        (PUSH_ENTITY, "off", "inhibited_by_push"),
        (GUARD_ENTITY, "off", "disarmed"),
        (RELAY_ENTITY, "unavailable", "relay_unavailable"),
    ],
)
def test_gates_are_rechecked_between_retries(
    guard_setup,
    changed_entity,
    new_state,
    expected_status,
):
    hass, _, manager = guard_setup

    def change_gate_after_first(attempt):
        if attempt == 1:
            hass.states.set(changed_entity, new_state)

    hass.services.on_call = change_gate_after_first

    assert _run(manager.async_check("relay_off")) == expected_status
    assert len(_turn_on_calls(hass)) == 1


def test_safe_mode_does_not_inhibit_recovery(guard_setup):
    hass, _, manager = guard_setup
    hass.states.set(
        "sensor.pumpsteer",
        SimpleNamespace(state="8.0", attributes={"mode": "safe_mode"}),
    )

    def succeed(attempt):
        if attempt == 1:
            hass.states.set(RELAY_ENTITY, "on")

    hass.services.on_call = succeed

    assert _run(manager.async_check("safe_mode")) == "healthy"
    assert len(_turn_on_calls(hass)) == 1


def test_repeated_scheduled_checks_do_not_overlap(guard_setup):
    hass, _, manager = guard_setup
    manager._started = True

    def succeed(attempt):
        if attempt == 1:
            hass.states.set(RELAY_ENTITY, "on")

    hass.services.on_call = succeed

    async def scenario():
        manager._schedule_check("first")
        task = manager._recovery_task
        assert task is not None

        manager._schedule_check("second")
        assert manager._recovery_task is task

        await task

    _run(scenario())
    assert len(_turn_on_calls(hass)) == 1


def test_start_and_stop_register_and_remove_all_listeners(guard_setup, monkeypatch):
    hass, _, manager = guard_setup
    removed = []
    state_callbacks = []

    def track_state(hass_obj, entity_ids, callback):
        state_callbacks.append((tuple(entity_ids), callback))

        def unsubscribe():
            removed.append("state")

        return unsubscribe

    def track_interval(hass_obj, callback, interval):
        def unsubscribe():
            removed.append("interval")

        return unsubscribe

    monkeypatch.setattr(relay_guard, "async_track_state_change_event", track_state)
    monkeypatch.setattr(relay_guard, "async_track_time_interval", track_interval)

    original_listen_once = hass.bus.async_listen_once

    def listen_once(event_type, callback):
        unsubscribe = original_listen_once(event_type, callback)

        def wrapped_unsubscribe():
            removed.append("startup")
            unsubscribe()

        return wrapped_unsubscribe

    hass.bus.async_listen_once = listen_once

    manager.async_start()
    assert len(state_callbacks) == 1
    assert RELAY_ENTITY in state_callbacks[0][0]
    assert PUSH_ENTITY in state_callbacks[0][0]

    _run(manager.async_stop())

    assert sorted(removed) == ["interval", "startup", "state"]


def test_unavailable_to_off_state_change_schedules_recovery(guard_setup, monkeypatch):
    hass, _, manager = guard_setup
    callbacks = []

    def track_state(hass_obj, entity_ids, callback):
        callbacks.append(callback)
        return lambda: None

    monkeypatch.setattr(relay_guard, "async_track_state_change_event", track_state)
    monkeypatch.setattr(
        relay_guard,
        "async_track_time_interval",
        lambda hass_obj, callback, interval: lambda: None,
    )

    def succeed(attempt):
        if attempt == 1:
            hass.states.set(RELAY_ENTITY, "on")

    hass.services.on_call = succeed

    async def scenario():
        manager.async_start()
        hass.states.set(RELAY_ENTITY, "off")
        event = SimpleNamespace(
            data={
                "old_state": SimpleNamespace(state="unavailable"),
                "new_state": SimpleNamespace(state="off"),
            }
        )
        callbacks[0](event)
        task = manager._recovery_task
        assert task is not None
        await task
        await manager.async_stop()

    _run(scenario())

    assert len(_turn_on_calls(hass)) == 1
