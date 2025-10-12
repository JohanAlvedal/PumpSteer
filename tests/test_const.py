import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401 - sets up Home Assistant stubs

from custom_components.pumpsteer.sensor import sensor


class DummyHass:
    pass


class DummyConfigEntry:
    entry_id = "test"

    def add_update_listener(self, listener):
        pass


def test_build_attributes_basic():
    sensor_data = {
        'aggressiveness': 3,
        'inertia': 2,
        'target_temp': 21.0,
        'indoor_temp': 20.5,
        'outdoor_temp': 5.0,
        'summer_threshold': 15.0,
        'outdoor_temp_forecast_entity': True,
    }
    prices = [1.2, 1.5, 1.1, 1.3]
    current_price = 1.2
    price_category = "normal"
    mode = "heating"
    holiday = False
    categories = ["normal", "high", "low", "normal"]
    now_hour = 1
    price_interval_minutes = 60
    current_slot_index = 0

    s = sensor.PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0

    attrs = s._build_attributes(
        sensor_data, prices, current_price, price_category, mode, holiday, categories, now_hour, price_interval_minutes, current_slot_index
    )
    assert attrs["mode"] == "heating"
    assert attrs["current_price"] == 1.2
    assert "aggressiveness" in attrs
    assert attrs["decision_reason"] == "heating - Triggered by temperature"


def test_decision_reason_very_cheap_heating():
    sensor_data = {
        'aggressiveness': 3,
        'inertia': 2,
        'target_temp': 21.0,
        'indoor_temp': 21.0,
        'outdoor_temp': 5.0,
        'summer_threshold': 15.0,
        'outdoor_temp_forecast_entity': True,
    }
    prices = [0.5, 0.6]
    current_price = 0.5
    price_category = "very_cheap"
    mode = "heating"
    holiday = False
    categories = ["very_cheap", "cheap"]
    now_hour = 0
    price_interval_minutes = 60
    current_slot_index = 0

    s = sensor.PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0

    attrs = s._build_attributes(
        sensor_data, prices, current_price, price_category, mode, holiday, categories, now_hour, price_interval_minutes, current_slot_index
    )
    assert attrs["decision_reason"] == "heating - Triggered by very cheap price"


def test_decision_reason_precool():
    sensor_data = {
        'aggressiveness': 3,
        'inertia': 2,
        'target_temp': 21.0,
        'indoor_temp': 21.0,
        'outdoor_temp': 5.0,
        'summer_threshold': 15.0,
        'outdoor_temp_forecast_entity': True,
    }
    prices = [1.0, 1.2]
    current_price = 1.0
    price_category = "normal"
    mode = "precool"
    holiday = False
    categories = ["normal", "high"]
    now_hour = 0
    price_interval_minutes = 60
    current_slot_index = 0

    s = sensor.PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0

    attrs = s._build_attributes(
        sensor_data, prices, current_price, price_category, mode, holiday, categories, now_hour, price_interval_minutes, current_slot_index
    )
    assert attrs["decision_reason"] == "precool - Triggered by pre-cool (warm forecast)"

