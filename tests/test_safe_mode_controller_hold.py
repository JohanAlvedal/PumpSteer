"""Short safe-mode outages keep controller memory; long ones start clean."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from test_preheat_brake_transition import _cycle, _sensor
from test_price_slot_integrity import _prices
from test_price_slot_integrity import _sensor as _price_sensor
from test_temperature_input_safety import control, setup_sensor  # noqa: F401

from custom_components.pumpsteer.settings import PID_KI

STOCKHOLM = ZoneInfo("Europe/Stockholm")
BASE = datetime(2026, 10, 11, 7, tzinfo=timezone.utc)


@pytest.fixture
def ctl(request):
    return request.getfixturevalue("control")


def _brake(sensor, monkeypatch, minutes):
    for minute in minutes:
        assert _cycle(sensor, monkeypatch, minute)["mode"] == "braking"
    return sensor._brake_ramp


# ── Short outages ─────────────────────────────────────────────────────────────


def test_short_sensor_dropout_during_braking_keeps_brake(monkeypatch):
    sensor, states = _sensor()
    factor = _brake(sensor, monkeypatch, range(60, 70))
    assert factor > 0.5

    states["sensor.indoor"].state = "unavailable"
    sample = _cycle(sensor, monkeypatch, 70)
    assert sample["mode"] == "safe_mode"
    assert sample["controller_state"] == "held"
    assert sensor._brake_ramp == factor
    assert sensor._was_braking_last_cycle is True

    states["sensor.indoor"].state = "20.5"
    sample = _cycle(sensor, monkeypatch, 71)
    assert sample["mode"] == "braking"
    # The ramp continues by one capped step instead of restarting from zero.
    assert factor < sensor._brake_ramp <= factor + 1 / 15 + 1e-9


def test_short_outage_keeps_pi_integral_without_integrating_the_gap(ctl):
    sensor, states, clock = ctl
    states["sensor.indoor"].state = "20.0"  # 1 K below the default target
    for _ in range(5):
        asyncio.run(sensor.async_update())
        clock[0] += timedelta(minutes=1)
    integral = sensor._pi._integral
    assert integral > 0.0

    states["sensor.outdoor"].state = "unavailable"
    for _ in range(10):
        asyncio.run(sensor.async_update())
        assert sensor.extra_state_attributes["controller_state"] == "held"
        clock[0] += timedelta(minutes=1)
    assert sensor._pi._integral == integral

    states["sensor.outdoor"].state = "-3.3"
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == "normal"
    # One minute since the last safe-mode cycle, not eleven.
    assert sensor._pi._integral == pytest.approx(integral + PID_KI * 1.0)


def test_safe_mode_output_is_unchanged_while_holding(ctl):
    sensor, states, _ = ctl
    asyncio.run(sensor.async_update())
    states["sensor.indoor"].state = "unavailable"
    asyncio.run(sensor.async_update())
    attrs = sensor.extra_state_attributes
    assert attrs["mode"] == "safe_mode"
    assert attrs["controller_state"] == "held"
    assert sensor.state == -3.3  # real outdoor passthrough
    assert sensor._last_pi_result is None


# ── Long outages ──────────────────────────────────────────────────────────────


def test_long_outage_resets_controller_state(monkeypatch):
    sensor, states = _sensor()
    _brake(sensor, monkeypatch, range(60, 70))
    states["sensor.indoor"].state = "unavailable"
    for minute in (70, 85, 99):
        assert _cycle(sensor, monkeypatch, minute)["controller_state"] == "held"
    sample = _cycle(sensor, monkeypatch, 100)  # 31 min after the last control
    assert sample["controller_state"] == "reset"
    assert sensor._brake_ramp == 0.0
    assert sensor._brake_last_expensive_t is None
    assert sensor._was_braking_last_cycle is False
    assert sensor._pi._integral == 0.0


def test_long_gap_before_recovery_also_resets(monkeypatch):
    # No safe-mode cycles in between (e.g. polling paused): the age of the held
    # memory is checked again when regular control resumes.
    sensor, states = _sensor()
    _brake(sensor, monkeypatch, range(60, 70))
    states["sensor.indoor"].state = "unavailable"
    assert _cycle(sensor, monkeypatch, 70)["controller_state"] == "held"
    states["sensor.indoor"].state = "20.5"
    sample = _cycle(sensor, monkeypatch, 105)
    assert sample["mode"] == "normal"
    assert sensor._brake_ramp == 0.0
    assert sensor._was_braking_last_cycle is False


def test_large_clock_jump_is_not_a_short_outage(monkeypatch):
    sensor, states = _sensor()
    _brake(sensor, monkeypatch, range(60, 70))
    states["sensor.indoor"].state = "unavailable"
    assert _cycle(sensor, monkeypatch, 70 - 120)["controller_state"] == "reset"


# ── Restart ───────────────────────────────────────────────────────────────────


def _restarted(monkeypatch, stored):
    sensor, states = _sensor()
    sensor.hass.is_running = False
    sensor.hass.bus = SimpleNamespace(async_listen_once=lambda *a: lambda: None)
    sensor._config_entry.add_update_listener = lambda callback: lambda: None

    async def last_extra():
        return SimpleNamespace(as_dict=lambda: dict(stored))

    sensor.async_get_last_extra_data = last_extra
    asyncio.run(sensor.async_added_to_hass())
    sensor._temperature_reported_after = None  # fresh-report gate tested elsewhere
    return sensor, states


def _stored(ramp, last_control_minutes_ago, *, with_control_t=True):
    restart = BASE + timedelta(minutes=70)
    last = restart - timedelta(minutes=last_control_minutes_ago)
    stored = {
        "brake_ramp": ramp,
        "brake_last_t": last.isoformat(),
        "brake_last_expensive_t": last.isoformat(),
        "was_braking_last_cycle": True,
    }
    if with_control_t:
        stored["last_control_t"] = last.isoformat()
    return stored


@pytest.mark.parametrize("with_control_t", [True, False])
def test_restart_during_braking_continues_restored_brake(monkeypatch, with_control_t):
    sensor, _ = _restarted(monkeypatch, _stored(0.8, 2, with_control_t=with_control_t))
    now = BASE + timedelta(minutes=70)
    asyncio.run(
        sensor._enter_safe_mode("Waiting for Home Assistant startup", None, now)
    )
    assert sensor.extra_state_attributes["controller_state"] == "held"
    assert sensor._brake_ramp == 0.8

    sample = _cycle(sensor, monkeypatch, 71)
    assert sample["mode"] == "braking"
    assert sensor._brake_ramp >= 0.8


def test_restart_after_long_downtime_starts_clean(monkeypatch):
    sensor, _ = _restarted(monkeypatch, _stored(0.8, 120))
    now = BASE + timedelta(minutes=70)
    asyncio.run(
        sensor._enter_safe_mode("Waiting for Home Assistant startup", None, now)
    )
    assert sensor.extra_state_attributes["controller_state"] == "reset"
    assert sensor._brake_ramp == 0.0


def test_restart_straight_into_valid_control_checks_age(monkeypatch):
    sensor, _ = _restarted(monkeypatch, _stored(0.8, 120))
    sample = _cycle(sensor, monkeypatch, 71)
    assert sample["mode"] == "braking"
    assert sensor._brake_ramp == pytest.approx(1 / 15)  # fresh ramp-in


def test_last_control_time_is_persisted(monkeypatch):
    sensor, _ = _sensor()
    _cycle(sensor, monkeypatch, 60)
    restore_module = __import__(
        "homeassistant.helpers.restore_state", fromlist=["ExtraStoredData"]
    )
    monkeypatch.setattr(restore_module, "ExtraStoredData", object, raising=False)
    saved = sensor.extra_restore_state_data.as_dict()
    assert saved["last_control_t"] == (BASE + timedelta(minutes=60)).isoformat()


# ── Midnight price rollover ───────────────────────────────────────────────────


def _day(day, interval=15, offset=0.0, timestamps=True):
    start = datetime(day.year, day.month, day.day, tzinfo=STOCKHOLM)
    end = (start + timedelta(days=1)).astimezone(timezone.utc)
    slot = start.astimezone(timezone.utc)
    items = []
    while slot < end:
        nxt = slot + timedelta(minutes=interval)
        value = round(offset + len(items) / 100, 2)
        items.append(
            {
                "start": slot.astimezone(STOCKHOLM).isoformat(),
                "end": nxt.astimezone(STOCKHOLM).isoformat(),
                "value": value,
            }
            if timestamps
            else value
        )
        slot = nxt
    return items


@pytest.mark.parametrize(
    ("day", "slots"),
    [(datetime(2026, 10, 20), 96), (datetime(2026, 10, 25), 100)],
)
def test_midnight_uses_tomorrow_list_when_it_is_today(day, slots):
    yesterday = day - timedelta(days=1)
    sensor = _price_sensor(_day(yesterday, offset=1.0), _day(day, offset=5.0))
    now = datetime(day.year, day.month, day.day, 0, 0, 4, tzinfo=STOCKHOLM)
    prices, _, interval, slot = _prices(sensor, now)
    assert len(prices) == slots
    assert interval == 15
    assert slot == 0
    assert sensor._current_price == 5.0  # today's first slot, not yesterday's


def test_midnight_rollover_needs_timestamps_to_prove_the_day():
    day = datetime(2026, 10, 20)
    sensor = _price_sensor(
        _day(day - timedelta(days=1), offset=1.0),
        _day(day, offset=5.0, timestamps=False),
    )
    now = datetime(2026, 10, 20, 0, 0, 4, tzinfo=STOCKHOLM)
    assert _prices(sensor, now) == ([], [], 60, 0)


def test_midnight_rollover_rejects_a_list_for_another_day():
    day = datetime(2026, 10, 20)
    sensor = _price_sensor(
        _day(day - timedelta(days=1), offset=1.0),
        _day(day + timedelta(days=1), offset=5.0),
    )
    now = datetime(2026, 10, 20, 0, 0, 4, tzinfo=STOCKHOLM)
    assert _prices(sensor, now) == ([], [], 60, 0)


def test_normal_day_still_uses_today_and_tomorrow():
    day = datetime(2026, 10, 20)
    sensor = _price_sensor(
        _day(day, offset=1.0), _day(day + timedelta(days=1), offset=5.0)
    )
    now = datetime(2026, 10, 20, 12, tzinfo=STOCKHOLM)
    prices, _, _, slot = _prices(sensor, now)
    assert len(prices) == 192
    assert slot == 48
    assert sensor._current_price == pytest.approx(1.48)
