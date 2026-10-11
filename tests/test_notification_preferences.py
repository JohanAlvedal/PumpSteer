"""Regression tests for price notification preferences and independent cooldowns."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401

from custom_components.pumpsteer import notify
from custom_components.pumpsteer.const import (
    NOTIFICATION_COOLDOWN_OPTION,
    NOTIFICATION_LEVEL_OPTION,
)


class _Registry:
    def async_get_entity_id(self, domain, _platform, _unique_id):
        if domain == "sensor":
            return "sensor.pumpsteer"
        if domain == "switch":
            return "switch.pumpsteer_notifications"
        return None


class _FakeStates:
    def __init__(self):
        self.notification_switch = "on"

    def get(self, entity_id):
        if entity_id == "switch.pumpsteer_notifications":
            return SimpleNamespace(state=self.notification_switch)
        return None


class _FakeHass:
    def __init__(self):
        self.states = _FakeStates()

    def async_create_task(self, coroutine):
        asyncio.run(coroutine)


def _setup(monkeypatch, options=None):
    """Register the real notification callback and intercept dispatched messages."""
    entry = SimpleNamespace(entry_id="test-entry", data={}, options=dict(options or {}))
    hass = _FakeHass()
    clock = [0.0]
    callbacks = []
    sent = []

    monkeypatch.setattr(notify.er, "async_get", lambda _hass: _Registry())
    monkeypatch.setattr(notify, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        notify,
        "async_track_state_change_event",
        lambda _hass, _entities, callback: callbacks.append(callback) or (lambda: None),
    )

    async def fake_send(_hass, _entry, title, message, _notification_id):
        sent.append((title, message))

    monkeypatch.setattr(notify, "async_send_notification", fake_send)
    unsubscribe = notify.async_setup_notifications(hass, entry)
    assert callable(unsubscribe)
    assert len(callbacks) == 1

    def emit(old_mode, new_mode, price=2.31):
        old_state = (
            SimpleNamespace(attributes={"mode": old_mode})
            if old_mode is not None
            else None
        )
        new_state = SimpleNamespace(
            attributes={
                "mode": new_mode,
                "current_price": price,
                "current_price_unit": "SEK/kWh",
            }
        )
        callbacks[0](
            SimpleNamespace(data={"old_state": old_state, "new_state": new_state})
        )

    return entry, hass, clock, sent, emit


def test_defaults_preserve_all_alerts_without_throttling(monkeypatch):
    _, _, clock, sent, emit = _setup(monkeypatch)
    emit("normal", "preheating", 0.68)
    clock[0] = 5
    emit("normal", "braking")
    clock[0] = 10
    emit("normal", "braking")

    assert len(sent) == 3
    assert "0.68 SEK/kWh" in sent[0][1]
    assert "2.31 SEK/kWh" in sent[1][1]


def test_only_braking_level_does_not_block_braking(monkeypatch):
    _, _, _, sent, emit = _setup(
        monkeypatch, {NOTIFICATION_LEVEL_OPTION: "braking_only"}
    )
    emit("normal", "preheating")
    emit("normal", "braking")
    assert len(sent) == 1
    assert "Price braking active" in sent[0][0]


@pytest.mark.parametrize("level", ["off", "invalid-setting"])
def test_level_off_or_invalid(monkeypatch, level):
    _, _, _, sent, emit = _setup(monkeypatch, {NOTIFICATION_LEVEL_OPTION: level})
    emit("normal", "preheating")
    emit("normal", "braking")
    assert len(sent) == (2 if level == "invalid-setting" else 0)


def test_master_notifications_switch_overrides_all(monkeypatch):
    _, hass, _, sent, emit = _setup(monkeypatch)
    hass.states.notification_switch = "off"
    emit("normal", "braking")
    emit("normal", "preheating")
    assert sent == []


def test_cooldown_per_mode_does_not_silence_opposite_mode(monkeypatch):
    _, _, clock, sent, emit = _setup(monkeypatch, {NOTIFICATION_COOLDOWN_OPTION: "60"})
    emit("normal", "preheating")
    clock[0] = 5 * 60
    emit("preheating", "braking")
    clock[0] = 10 * 60
    emit("normal", "preheating")
    emit("normal", "braking")
    assert len(sent) == 2

    clock[0] = 60 * 60
    emit("normal", "preheating")
    assert len(sent) == 3
    clock[0] = 65 * 60
    emit("normal", "braking")
    assert len(sent) == 4


@pytest.mark.parametrize("minutes", ["30", "120"])
def test_cooldown_boundaries(monkeypatch, minutes):
    _, _, clock, sent, emit = _setup(
        monkeypatch, {NOTIFICATION_COOLDOWN_OPTION: minutes}
    )
    emit("normal", "braking")
    clock[0] = int(minutes) * 60 - 0.001
    emit("normal", "braking")
    assert len(sent) == 1
    clock[0] = int(minutes) * 60
    emit("normal", "braking")
    assert len(sent) == 2


@pytest.mark.parametrize("invalid", ["banana", "-30", "999", None])
def test_invalid_cooldown_fails_open_without_crashing(monkeypatch, invalid):
    _, _, _, sent, emit = _setup(monkeypatch, {NOTIFICATION_COOLDOWN_OPTION: invalid})
    emit("normal", "braking")
    emit("normal", "braking")
    assert len(sent) == 2


def test_mode_unchanged_or_unrelated_mode_never_notifies(monkeypatch):
    _, _, _, sent, emit = _setup(monkeypatch)
    emit("braking", "braking")
    emit("normal", "brake_hold")
    emit("normal", "pre_braking")
    emit("normal", "normal")
    assert sent == []


def test_options_changes_apply_without_reloading_listener(monkeypatch):
    entry, _, clock, sent, emit = _setup(
        monkeypatch,
        {
            NOTIFICATION_LEVEL_OPTION: "braking_only",
            NOTIFICATION_COOLDOWN_OPTION: "120",
        },
    )
    emit("normal", "preheating")
    emit("normal", "braking")
    assert len(sent) == 1

    entry.options[NOTIFICATION_LEVEL_OPTION] = "all"
    entry.options[NOTIFICATION_COOLDOWN_OPTION] = "0"
    clock[0] = 10
    emit("normal", "preheating")
    emit("normal", "braking")
    assert len(sent) == 3


def test_preheating_missing_price_falls_back_to_text(monkeypatch):
    _, _, _, sent, emit = _setup(monkeypatch)
    emit("normal", "preheating", "unavailable")
    assert len(sent) == 1
    assert "upcoming expensive period" in sent[0][1]
    assert "Current price" not in sent[0][1]
