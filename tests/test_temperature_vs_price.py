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


class DummyHass:
    pass


class DummyConfigEntry:
    entry_id = "test"

    def add_update_listener(self, listener):
        pass


def create_sensor():
    return sensor.PumpSteerSensor(DummyHass(), DummyConfigEntry())


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
