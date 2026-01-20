import sys
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
    current_price = 1.2
    price_category = "normal"
    mode = "heating"
    holiday = False
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

    decision_reason = s._get_decision_reason(mode, price_category)
    attrs = s._build_attributes(
        sensor_data,
        current_price,
        price_category,
        mode,
        holiday,
        price_interval_minutes=60,
        pi_data=pi_data,
        decision_reason=decision_reason,
        brake_offset_c=0.0,
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
    current_price = 0.5
    price_category = "very_cheap"
    mode = "heating"
    holiday = False
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

    decision_reason = s._get_decision_reason(mode, price_category)
    attrs = s._build_attributes(
        sensor_data,
        current_price,
        price_category,
        mode,
        holiday,
        price_interval_minutes=60,
        pi_data=pi_data,
        decision_reason=decision_reason,
        brake_offset_c=0.0,
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
    current_price = 1.0
    price_category = "normal"
    mode = "precool"
    holiday = False
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

    decision_reason = s._get_decision_reason(mode, price_category)
    attrs = s._build_attributes(
        sensor_data,
        current_price,
        price_category,
        mode,
        holiday,
        price_interval_minutes=60,
        pi_data=pi_data,
        decision_reason=decision_reason,
        brake_offset_c=0.0,
    )
    assert attrs["decision_reason"] == "precool - Triggered by pre-cool (warm forecast)"
