"""Regression tests for short price-dip brake bridging."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.electricity_price import (
    PRICE_EXPENSIVE,
    PRICE_NORMAL,
)
from custom_components.pumpsteer.sensor import MODE_PI, PumpSteerSensor


class _DummyState:
    def __init__(self, state):
        self.state = state
        self.attributes = {}


class _DummyStates:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        value = self._mapping.get(entity_id)
        return _DummyState(value) if value is not None else None


class _DummyHass:
    def __init__(self):
        self.states = _DummyStates(
            {
                "sensor.indoor": "21.0",
                "sensor.outdoor": "5.0",
            }
        )


def _make_sensor(brake_hold_minutes=30.0):
    entry = SimpleNamespace(
        entry_id="test-entry",
        data={},
        options={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "electricity_price_entity": "sensor.price",
            "price_tomorrow_entity": "sensor.price_tomorrow",
            "target_temperature": 21.0,
            "summer_threshold": 18.0,
            "aggressiveness": 3.0,
            "house_inertia": 2.0,
            "preheat_boost_enabled": False,
            "brake_hold_minutes": brake_hold_minutes,
        },
    )
    return PumpSteerSensor(_DummyHass(), entry)


def _run_cycle(sensor, monkeypatch, now, categories, forecast_temps=None):
    async def fake_holiday(*args, **kwargs):
        return False

    async def fake_prices(cfg, update_time):
        return (
            [1.0] * len(categories),
            categories,
            15,
            0,
        )

    async def fake_forecast():
        return forecast_temps

    captured = {}

    async def fake_set_state(fake_temp, mode, extra, update_time):
        captured["fake_temp"] = fake_temp
        captured["mode"] = mode
        captured["extra"] = extra

    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)
    monkeypatch.setattr(sensor_module, "async_update_holiday", fake_holiday)
    monkeypatch.setattr(sensor, "_get_prices", fake_prices)
    monkeypatch.setattr(sensor, "_forecast_temps", fake_forecast)
    monkeypatch.setattr(sensor, "_set_state", fake_set_state)

    asyncio.run(sensor._do_update())
    return captured


def test_short_dip_holds_existing_brake_factor_without_ramping(monkeypatch):
    sensor = _make_sensor(brake_hold_minutes=30.0)
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)
    sensor._brake_ramp = 0.5
    sensor._brake_last_t = now - timedelta(minutes=1)

    captured = _run_cycle(
        sensor,
        monkeypatch,
        now,
        [PRICE_NORMAL, PRICE_EXPENSIVE],
        forecast_temps=[0.0] * 6,
    )

    assert captured["mode"] == MODE_PI
    assert captured["extra"]["bridge_short_dip"] is True
    assert captured["extra"]["minutes_until_expensive"] == 5.0
    assert sensor._brake_ramp == 0.5


def test_long_dip_releases_brake_instead_of_bridging(monkeypatch):
    sensor = _make_sensor(brake_hold_minutes=30.0)
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)
    sensor._brake_ramp = 0.5
    sensor._brake_last_t = now - timedelta(minutes=1)

    captured = _run_cycle(
        sensor,
        monkeypatch,
        now,
        [
            PRICE_NORMAL,
            PRICE_NORMAL,
            PRICE_NORMAL,
            PRICE_EXPENSIVE,
        ],
    )

    assert captured["mode"] == MODE_PI
    assert captured["extra"]["bridge_short_dip"] is False
    assert captured["extra"]["minutes_until_expensive"] == 35.0
    assert sensor._brake_ramp < 0.5


def test_bridge_uses_configured_hold_window(monkeypatch):
    sensor = _make_sensor(brake_hold_minutes=45.0)
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)
    sensor._brake_ramp = 0.5
    sensor._brake_last_t = now - timedelta(minutes=1)

    captured = _run_cycle(
        sensor,
        monkeypatch,
        now,
        [
            PRICE_NORMAL,
            PRICE_NORMAL,
            PRICE_NORMAL,
            PRICE_EXPENSIVE,
        ],
    )

    assert captured["extra"]["bridge_short_dip"] is True
    assert captured["extra"]["bridge_limit_minutes"] == 45.0
    assert sensor._brake_ramp == 0.5
