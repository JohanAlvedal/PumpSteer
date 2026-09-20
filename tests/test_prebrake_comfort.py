"""Regression tests for comfort-floor protection around pre-brake."""

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
                "sensor.indoor": "19.0",
                "sensor.outdoor": "5.0",
            }
        )


def _make_sensor():
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
        },
    )
    return PumpSteerSensor(_DummyHass(), entry)


def _run_control_cycle(sensor, monkeypatch, now):
    async def fake_holiday(*args, **kwargs):
        return False

    async def fake_prices(cfg, update_time):
        return (
            [1.0, 3.0],
            [PRICE_NORMAL, PRICE_EXPENSIVE],
            15,
            0,
        )

    async def fake_forecast():
        return None

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


def test_prebrake_does_not_start_below_comfort_floor(monkeypatch):
    sensor = _make_sensor()
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)

    captured = _run_control_cycle(sensor, monkeypatch, now)

    assert captured["mode"] == MODE_PI
    assert sensor._brake_ramp == 0.0


def test_existing_prebrake_ramps_out_below_comfort_floor(monkeypatch):
    sensor = _make_sensor()
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)
    sensor._brake_ramp = 0.5
    sensor._brake_last_t = now - timedelta(minutes=1)

    captured = _run_control_cycle(sensor, monkeypatch, now)

    assert captured["mode"] == MODE_PI
    assert sensor._brake_ramp < 0.5
    assert captured["extra"]["bridge_short_dip"] is False
