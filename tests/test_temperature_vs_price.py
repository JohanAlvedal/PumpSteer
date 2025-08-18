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
    assert fake_temp == sensor.BRAKING_MODE_TEMP
