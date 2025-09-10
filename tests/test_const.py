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
    categories = ["normal", "high", "low"]
    now_hour = 1

    s = sensor.PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0

    attrs = s._build_attributes(sensor_data, prices, current_price, price_category, mode, holiday, categories, now_hour)
    assert attrs["mode"] == "heating"
    assert attrs["current_price"] == 1.2
    assert "aggressiveness" in attrs


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

    s = sensor.PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0

    attrs = s._build_attributes(sensor_data, prices, current_price, price_category, mode, holiday, categories, now_hour)
    assert attrs["decision_reason"] == "heating - Triggered by very cheap price"