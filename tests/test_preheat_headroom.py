"""Regression tests for saving-level preheat thermal headroom."""

import asyncio
import sys
from datetime import datetime, timezone
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
from custom_components.pumpsteer.sensor import MODE_PI, MODE_PREHEAT, PumpSteerSensor
from custom_components.pumpsteer.settings import PREHEAT_HEADROOM_BY_AGGRESSIVENESS


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
    def __init__(self, indoor):
        self.states = _DummyStates(
            {
                "sensor.indoor": str(indoor),
                "sensor.outdoor": "5.0",
            }
        )


def _make_sensor(indoor, aggressiveness=3):
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
            "aggressiveness": aggressiveness,
            "house_inertia": 2.0,
            "preheat_boost_enabled": True,
        },
    )
    return PumpSteerSensor(_DummyHass(indoor), entry)


def _run_preheat_cycle(sensor, monkeypatch, now):
    async def fake_holiday(*args, **kwargs):
        return False

    async def fake_prices(cfg, update_time):
        return (
            [1.0, 1.0, 3.0],
            [PRICE_NORMAL, PRICE_NORMAL, PRICE_EXPENSIVE],
            15,
            0,
        )

    async def fake_forecast():
        return [0.0] * 6

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


def test_preheat_headroom_mapping_increases_with_saving_level():
    assert PREHEAT_HEADROOM_BY_AGGRESSIVENESS == [0.0, 0.3, 0.5, 0.7, 1.0, 1.5]


def test_headroom_factor_full_at_or_below_target():
    factor = PumpSteerSensor._preheat_headroom_factor(
        indoor=20.5,
        target=21.0,
        headroom=0.7,
    )

    assert factor == 1.0


def test_headroom_factor_tapers_linearly_above_target():
    factor = PumpSteerSensor._preheat_headroom_factor(
        indoor=21.35,
        target=21.0,
        headroom=0.7,
    )

    assert factor == 0.5


def test_headroom_factor_zero_at_ceiling():
    factor = PumpSteerSensor._preheat_headroom_factor(
        indoor=21.7,
        target=21.0,
        headroom=0.7,
    )

    assert factor == 0.0


def test_preheat_runs_with_full_headroom_below_target(monkeypatch):
    sensor = _make_sensor(indoor=20.0, aggressiveness=3)
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)

    captured = _run_preheat_cycle(sensor, monkeypatch, now)

    assert captured["mode"] == MODE_PREHEAT
    assert captured["extra"]["preheat_headroom_c"] == 0.7
    assert captured["extra"]["preheat_ceiling_c"] == 21.7
    assert captured["extra"]["preheat_headroom_factor"] == 1.0
    assert captured["extra"]["preheat_boost_c"] > 0.0


def test_preheat_boost_is_reduced_halfway_to_ceiling(monkeypatch):
    sensor = _make_sensor(indoor=21.35, aggressiveness=3)
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)

    captured = _run_preheat_cycle(sensor, monkeypatch, now)

    assert captured["mode"] == MODE_PREHEAT
    assert captured["extra"]["preheat_headroom_factor"] == 0.5
    assert captured["extra"]["preheat_boost_c"] > 0.0


def test_preheat_stops_at_headroom_ceiling(monkeypatch):
    sensor = _make_sensor(indoor=21.7, aggressiveness=3)
    now = datetime(2026, 9, 20, 8, 10, tzinfo=timezone.utc)

    captured = _run_preheat_cycle(sensor, monkeypatch, now)

    assert captured["mode"] == MODE_PI
    assert captured["extra"]["preheat_headroom_factor"] == 0.0
    assert captured["extra"]["preheat_ceiling_c"] == 21.7
