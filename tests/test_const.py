import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))


from custom_components.pumpsteer.sensor import sensor


class DummyHass:
    def __init__(self):
        self.data = {}


class DummyConfigEntry:
    entry_id = "test"

    def add_update_listener(self, listener):
        pass


def test_build_attributes_basic():
    sensor_data = {
        "aggressiveness": 3,
        "inertia": 2,
        "target_temp": 21.0,
        "indoor_temp": 20.5,
        "outdoor_temp": 5.0,
        "summer_threshold": 15.0,
        "outdoor_temp_forecast_entity": True,
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
    s._attr_native_value = 5.0

    pi_data = {
        "price_brake_level": 0.0,
        "price_baseline": 0.0,
        "price_threshold": 0.0,
        "price_area": 0.0,
        "price_amplitude": 0.0,
        "price_block": None,
        "price_block_start": None,
        "price_block_end": None,
        "in_price_block": False,
        "block_state": "none",
        "price_rate_limited": False,
        "comfort_push": 0.0,
        "comfort_I": 0.0,
        "temp_error": 0.0,
        "dt_minutes": 60,
        "brake_blocked_reason": "no_price_block",
    }

    attrs = s._build_attributes(
        sensor_data,
        prices,
        current_price,
        price_category,
        mode,
        holiday,
        categories,
        now_hour,
        price_interval_minutes=60,
        current_slot_index=0,
        pi_data=pi_data,
        final_adjust=0.0,
        update_time=datetime(2024, 1, 1, now_hour, 0, 0),
    )
    assert attrs["mode"] == "heating"
    assert attrs["current_price"] == 1.2
    assert "aggressiveness" in attrs
    assert attrs["decision_reason"] == "heating - Triggered by temperature"


def test_decision_reason_very_cheap_heating():
    sensor_data = {
        "aggressiveness": 3,
        "inertia": 2,
        "target_temp": 21.0,
        "indoor_temp": 21.0,
        "outdoor_temp": 5.0,
        "summer_threshold": 15.0,
        "outdoor_temp_forecast_entity": True,
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
    s._attr_native_value = 5.0

    pi_data = {
        "price_brake_level": 0.0,
        "price_baseline": 0.0,
        "price_threshold": 0.0,
        "price_area": 0.0,
        "price_amplitude": 0.0,
        "price_block": None,
        "price_block_start": None,
        "price_block_end": None,
        "in_price_block": False,
        "block_state": "none",
        "price_rate_limited": False,
        "comfort_push": 0.0,
        "comfort_I": 0.0,
        "temp_error": 0.0,
        "dt_minutes": 60,
        "brake_blocked_reason": "no_price_block",
    }

    attrs = s._build_attributes(
        sensor_data,
        prices,
        current_price,
        price_category,
        mode,
        holiday,
        categories,
        now_hour,
        price_interval_minutes=60,
        current_slot_index=0,
        pi_data=pi_data,
        final_adjust=0.0,
        update_time=datetime(2024, 1, 1, now_hour, 0, 0),
    )
    assert attrs["decision_reason"] == "heating - Triggered by very cheap price"


def test_decision_reason_precool():
    sensor_data = {
        "aggressiveness": 3,
        "inertia": 2,
        "target_temp": 21.0,
        "indoor_temp": 21.0,
        "outdoor_temp": 5.0,
        "summer_threshold": 15.0,
        "outdoor_temp_forecast_entity": True,
    }
    prices = [1.0, 1.2]
    current_price = 1.0
    price_category = "normal"
    mode = "precool"
    holiday = False
    categories = ["normal", "high"]
    now_hour = 0

    s = sensor.PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0
    s._attr_native_value = 5.0

    pi_data = {
        "price_brake_level": 0.0,
        "price_baseline": 0.0,
        "price_threshold": 0.0,
        "price_area": 0.0,
        "price_amplitude": 0.0,
        "price_block": None,
        "price_block_start": None,
        "price_block_end": None,
        "in_price_block": False,
        "block_state": "none",
        "price_rate_limited": False,
        "comfort_push": 0.0,
        "comfort_I": 0.0,
        "temp_error": 0.0,
        "dt_minutes": 60,
        "brake_blocked_reason": "no_price_block",
    }

    attrs = s._build_attributes(
        sensor_data,
        prices,
        current_price,
        price_category,
        mode,
        holiday,
        categories,
        now_hour,
        price_interval_minutes=60,
        current_slot_index=0,
        pi_data=pi_data,
        final_adjust=0.0,
        update_time=datetime(2024, 1, 1, now_hour, 0, 0),
    )
    assert attrs["decision_reason"] == "precool - Triggered by pre-cool (warm forecast)"
