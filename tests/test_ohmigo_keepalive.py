"""Regression tests for Ohmigo pushes that also keep its watchdog alive."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import ohmigo


class _FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))


class _FakeHass:
    def __init__(self, current_state):
        self.current_state = current_state
        self.services = _FakeServices()
        self.states = SimpleNamespace(get=self._get_state)

    def _get_state(self, entity_id):
        assert entity_id == "number.ohmigo_test"
        if self.current_state is None:
            return None
        return SimpleNamespace(state=self.current_state)


@pytest.fixture
def setup_push(monkeypatch):
    clock = [datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)]
    logbook_calls = []
    monkeypatch.setattr(ohmigo.dt_util, "now", lambda: clock[0])
    monkeypatch.setattr(ohmigo, "_ohmigo_push_enabled", lambda hass, entry_id: True)
    components = __import__("homeassistant.components", fromlist=["logbook"])

    def log_entry(*args, **kwargs):
        logbook_calls.append(kwargs)

    monkeypatch.setattr(
        components,
        "logbook",
        SimpleNamespace(async_log_entry=log_entry),
        raising=False,
    )
    entry = SimpleNamespace(
        entry_id="test-entry",
        data={},
        options={"ohmigo_entity": "number.ohmigo_test", "ohmigo_interval_minutes": 5},
    )
    return clock, logbook_calls, entry


def _push(hass, entry, last_push_time):
    return asyncio.run(ohmigo.async_push_ohmigo(hass, entry, 21.49, last_push_time))


def _expected_call():
    return (
        "number",
        "set_value",
        {"entity_id": "number.ohmigo_test", "value": 21.5},
        True,
    )


def test_changed_setpoint_and_due_keepalive_without_logbook_spam(setup_push, caplog):
    clock, logbook_calls, entry = setup_push
    hass = _FakeHass("20.0")

    with caplog.at_level(logging.DEBUG, logger=ohmigo.__name__):
        last_push = _push(hass, entry, None)
        assert last_push == clock[0]
        assert hass.services.calls == [_expected_call()]
        assert len(logbook_calls) == 1

        hass.current_state = "21.5"
        clock[0] += timedelta(minutes=4)
        assert _push(hass, entry, last_push) == last_push
        assert hass.services.calls == [_expected_call()]

        clock[0] += timedelta(minutes=1)
        assert _push(hass, entry, last_push) == clock[0]

    assert hass.services.calls == [_expected_call(), _expected_call()]
    assert len(logbook_calls) == 1
    assert "Ohmigo keepalive resend" in caplog.text


def test_push_off_sends_nothing(setup_push, monkeypatch):
    _, logbook_calls, entry = setup_push
    monkeypatch.setattr(ohmigo, "_ohmigo_push_enabled", lambda hass, entry_id: False)
    hass = _FakeHass("20.0")

    assert _push(hass, entry, None) is None
    assert hass.services.calls == []
    assert logbook_calls == []


@pytest.mark.parametrize("current_state", [None, "unknown", "unavailable", "invalid"])
def test_missing_or_invalid_state_still_pushes(setup_push, current_state):
    clock, logbook_calls, entry = setup_push
    hass = _FakeHass(current_state)

    assert _push(hass, entry, None) == clock[0]
    assert hass.services.calls == [_expected_call()]
    assert len(logbook_calls) == 1


def _push_value(hass, entry, fake_temp):
    asyncio.run(ohmigo.async_push_ohmigo(hass, entry, fake_temp, None))
    return hass.services.calls[-1][2]["value"]


@pytest.mark.parametrize("fake_temp", [-3.26, -3.3, -3.34, -2.9, -2.66])
def test_step_is_held_near_boundary(setup_push, fake_temp):
    """Raw values within 0.35 °C of the current step keep that step."""
    _, _, entry = setup_push
    hass = _FakeHass("-3.0")

    assert _push_value(hass, entry, fake_temp) == -3.0


@pytest.mark.parametrize(
    ("fake_temp", "expected"),
    [(-3.36, -3.5), (-2.64, -2.5), (-3.4, -3.5), (-4.2, -4.0)],
)
def test_step_changes_beyond_hysteresis(setup_push, fake_temp, expected):
    _, _, entry = setup_push
    hass = _FakeHass("-3.0")

    assert _push_value(hass, entry, fake_temp) == expected


def test_no_flip_flop_around_boundary(setup_push):
    """Noise around a step boundary must not toggle the written value."""
    _, _, entry = setup_push
    hass = _FakeHass("-3.0")
    written = []
    for fake_temp in [-3.2, -3.3, -3.24, -3.31, -3.27, -3.22, -3.29]:
        value = _push_value(hass, entry, fake_temp)
        hass.current_state = str(value)
        written.append(value)

    assert written == [-3.0] * 7


def test_off_grid_current_value_is_not_held(setup_push):
    """A value PumpSteer did not write is replaced by the rounded value."""
    _, _, entry = setup_push
    hass = _FakeHass("-3.1")

    assert _push_value(hass, entry, -3.2) == -3.0
