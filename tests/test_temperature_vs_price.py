import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401 - sets up Home Assistant stubs

from custom_components.pumpsteer.sensor import sensor
from custom_components.pumpsteer.temp_control_logic import calculate_temperature_output
from custom_components.pumpsteer.settings import (
    BRAKE_FAKE_TEMP,
    HEATING_COMPENSATION_FACTOR,
)
import pytest


class DummyState:
    def __init__(self, state):
        self.state = state


class DummyStates:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        value = self._mapping.get(entity_id)
        return DummyState(value) if value is not None else None


class DummyHass:
    def __init__(self, states=None):
        self.states = DummyStates(states or {})


class DummyConfigEntry:
    entry_id = "test"

    def add_update_listener(self, listener):
        pass


def create_sensor(hass=None):
    return sensor.PumpSteerSensor(hass or DummyHass(), DummyConfigEntry())


def base_sensor_data(**kwargs):
    data = {
        "indoor_temp": 21.0,
        "target_temp": 21.0,
        "outdoor_temp": 5.0,
        "summer_threshold": 18.0,
        "aggressiveness": 3.0,
        "inertia": 1.0,
        "outdoor_temp_forecast_entity": None,
        "preboost_enabled": False,
    }
    data.update(kwargs)
    return data


def test_heating_not_blocked_by_expensive_price():
    s = create_sensor()
    data = base_sensor_data(indoor_temp=19.0, target_temp=21.0)
    fake_temp, mode = s._calculate_output_temperature(data, [], "very_expensive", 0)
    assert mode == "heating"
    assert fake_temp < data["outdoor_temp"]


def test_price_brake_when_neutral():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode = s._calculate_output_temperature(data, [], "expensive", 0)
    assert mode == "braking_by_price"
    assert fake_temp == data["outdoor_temp"] + sensor.WINTER_BRAKE_TEMP_OFFSET


def test_extreme_price_brake_when_neutral():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode = s._calculate_output_temperature(data, [], "extreme", 0)
    assert mode == "braking_by_price"
    assert fake_temp == data["outdoor_temp"] + sensor.WINTER_BRAKE_TEMP_OFFSET


def test_very_cheap_price_overshoots_target():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode = s._calculate_output_temperature(data, [], "very_cheap", 0)
    assert mode == "heating"
    assert fake_temp < data["outdoor_temp"]


def test_cheap_price_neutral_behavior():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode = s._calculate_output_temperature(data, [], "cheap", 0)
    assert mode == "neutral"
    assert fake_temp == data["outdoor_temp"]


def test_precool_triggered_by_forecast():
    forecast = "17,19,17"
    hass = DummyHass({"input_text.hourly_forecast_temperatures": forecast})
    s = create_sensor(hass)
    data = base_sensor_data(outdoor_temp_forecast_entity="input_text.hourly_forecast_temperatures")
    fake_temp, mode = s._calculate_output_temperature(data, [], "normal", 0)
    assert mode == "precool"
    assert fake_temp == BRAKE_FAKE_TEMP


def test_precool_triggered_by_long_term_forecast():
    forecast = "17,17,17,17,17,17,19"
    hass = DummyHass({"input_text.hourly_forecast_temperatures": forecast})
    s = create_sensor(hass)
    data = base_sensor_data(outdoor_temp_forecast_entity="input_text.hourly_forecast_temperatures")
    fake_temp, mode = s._calculate_output_temperature(data, [], "normal", 0)
    assert mode == "precool"
    assert fake_temp == BRAKE_FAKE_TEMP


def test_heating_compensation_factor_applied():
    fake_temp, mode = calculate_temperature_output(
        indoor_temp=19.0,
        actual_target_temp_for_logic=21.0,
        real_outdoor_temp=5.0,
        aggressiveness=3.0,
        brake_temp=BRAKE_FAKE_TEMP,
    )
    expected = 5.0 + (19.0 - 21.0) * 3.0 * HEATING_COMPENSATION_FACTOR
    assert mode == "heating"
    assert round(fake_temp, 6) == round(expected, 6)


def test_fake_temp_constraint_applied():
    """Test that fake_temp is constrained to not exceed BRAKE_FAKE_TEMP."""
    s = create_sensor()
    # Create a scenario that might produce high fake_temp values
    # Use very high indoor temperature and neutral target to trigger braking mode
    data = base_sensor_data(
        indoor_temp=30.0,  # Very high indoor temp
        target_temp=20.0,  # Much lower target
        outdoor_temp=5.0,  # Cold outdoor temp
        aggressiveness=5.0  # Maximum aggressiveness
    )
    fake_temp, mode = s._calculate_output_temperature(data, [], "normal", 0)
    
    # The fake_temp should be constrained to BRAKE_FAKE_TEMP (25.0)
    assert fake_temp <= BRAKE_FAKE_TEMP
    assert fake_temp == BRAKE_FAKE_TEMP  # Should be exactly BRAKE_FAKE_TEMP due to constraint
