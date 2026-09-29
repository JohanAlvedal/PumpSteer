"""Tests for exact current-price propagation into braking notifications."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.notify import (
    MODE_NOTIFICATIONS,
    _notification_content,
)
from custom_components.pumpsteer.sensor import PumpSteerSensor


class _DummyState:
    def __init__(self, state=None, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class _DummyStates:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        return self._mapping.get(entity_id)


class _DummyHass:
    def __init__(self):
        self.states = _DummyStates(
            {
                "sensor.price": _DummyState(
                    "2.31",
                    {
                        "today": [0.40, 2.31, 0.80],
                        "unit_of_measurement": "SEK/kWh",
                    },
                ),
                "sensor.price_tomorrow": _DummyState(
                    "1.00",
                    {"tomorrow": []},
                ),
            }
        )


def _make_sensor():
    entry = SimpleNamespace(
        entry_id="test-entry",
        data={},
        options={
            "electricity_price_entity": "sensor.price",
            "price_tomorrow_entity": "sensor.price_tomorrow",
        },
    )
    return PumpSteerSensor(_DummyHass(), entry)


def test_current_price_comes_from_same_snapshot_and_slot(monkeypatch):
    sensor = _make_sensor()
    now = datetime(2026, 9, 29, 10, 15, tzinfo=timezone.utc)

    async def fake_thresholds(_prices):
        return 0.50, 2.00

    monkeypatch.setattr(sensor_module, "async_get_price_thresholds", fake_thresholds)
    monkeypatch.setattr(sensor_module, "detect_price_interval_minutes", lambda _: 15)
    monkeypatch.setattr(
        sensor_module,
        "compute_price_slot_index",
        lambda _now, _interval, _count: 1,
    )
    monkeypatch.setattr(
        sensor_module,
        "filter_short_peaks",
        lambda categories, _interval, _minimum: categories,
    )

    prices, categories, _interval, current_slot = asyncio.run(
        sensor._get_prices(sensor._cfg(), now)
    )

    assert current_slot == 1
    assert prices[current_slot] == 2.31
    assert categories[current_slot] == "expensive"
    assert sensor._current_price == prices[current_slot]
    assert sensor._current_price_unit == "SEK/kWh"

    attrs = sensor._base_attrs(20.0, 21.0, 5.0, categories[current_slot], 3)
    assert attrs["current_price"] == 2.31
    assert attrs["current_price_unit"] == "SEK/kWh"


def test_braking_notification_includes_exact_price_and_unit():
    state = _DummyState(
        attributes={
            "mode": "braking",
            "current_price": 2.31,
            "current_price_unit": "SEK/kWh",
        }
    )

    title, message = _notification_content("braking", state)

    assert title == MODE_NOTIFICATIONS["braking"][0]
    assert message == (
        "Electricity is expensive — heating has been reduced.\n"
        "Current price: 2.31 SEK/kWh"
    )


def test_braking_notification_falls_back_when_price_missing():
    state = _DummyState(attributes={"mode": "braking"})

    assert _notification_content("braking", state) == MODE_NOTIFICATIONS["braking"]


def test_braking_notification_falls_back_for_invalid_price():
    state = _DummyState(
        attributes={
            "mode": "braking",
            "current_price": "unavailable",
            "current_price_unit": "SEK/kWh",
        }
    )

    assert _notification_content("braking", state) == MODE_NOTIFICATIONS["braking"]


def test_preheating_notification_is_unchanged():
    state = _DummyState(
        attributes={
            "mode": "preheating",
            "current_price": 0.25,
            "current_price_unit": "SEK/kWh",
        }
    )

    assert _notification_content("preheating", state) == MODE_NOTIFICATIONS["preheating"]
