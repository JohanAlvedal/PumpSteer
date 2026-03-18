import sys
from datetime import datetime, timedelta
from pathlib import Path

from custom_components.pumpsteer.sensor import sensor
from custom_components.pumpsteer.temp_control_logic import calculate_temperature_output
from custom_components.pumpsteer.settings import (
    BRAKE_FAKE_TEMP,
    HEATING_COMPENSATION_FACTOR,
    WINTER_BRAKE_TEMP_OFFSET,
    WINTER_BRAKE_THRESHOLD,
    PRECOOL_MARGIN,
)

from custom_components.pumpsteer import settings

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))


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
    }
    data.update(kwargs)
    return data


def test_heating_not_blocked_by_expensive_price():
    s = create_sensor()
    data = base_sensor_data(indoor_temp=19.0, target_temp=21.0)
    fake_temp, mode, debug = s._calculate_output_temperature(
        data,
        "very_expensive",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    assert mode == "pid"
    assert debug["brake_requested"] is False
    assert fake_temp < data["outdoor_temp"]


def test_price_brake_when_neutral():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode, debug = s._calculate_output_temperature(
        data,
        "expensive",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    assert mode == "brake_ramp_in"
    assert debug["brake_reason"] == "price"
    expected = (
        data["outdoor_temp"] + WINTER_BRAKE_TEMP_OFFSET
        if data["outdoor_temp"] < WINTER_BRAKE_THRESHOLD
        else BRAKE_FAKE_TEMP
    )
    assert data["outdoor_temp"] < fake_temp < expected


def test_extreme_price_brake_when_neutral():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "extreme",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    assert mode == "brake_ramp_in"
    expected = (
        data["outdoor_temp"] + WINTER_BRAKE_TEMP_OFFSET
        if data["outdoor_temp"] < WINTER_BRAKE_THRESHOLD
        else BRAKE_FAKE_TEMP
    )
    assert data["outdoor_temp"] < fake_temp < expected


def test_very_cheap_price_overshoots_target():
    s = create_sensor()
    data = base_sensor_data()
    original_overshoot = sensor.CHEAP_PRICE_OVERSHOOT
    sensor.CHEAP_PRICE_OVERSHOOT = 0.6
    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "very_cheap",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    sensor.CHEAP_PRICE_OVERSHOOT = original_overshoot
    assert mode == "pid"
    assert fake_temp < data["outdoor_temp"]


def test_cheap_price_neutral_behavior():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "cheap",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    assert mode == "pid"
    assert fake_temp == data["outdoor_temp"]


def test_precool_triggered_by_forecast():
    st = base_sensor_data()["summer_threshold"]
    trigger = st + PRECOOL_MARGIN
    forecast = f"{st - 1},{trigger},{st - 1}"
    hass = DummyHass({"input_text.hourly_forecast_temperatures": forecast})
    s = create_sensor(hass)
    data = base_sensor_data(
        outdoor_temp_forecast_entity="input_text.hourly_forecast_temperatures"
    )
    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "normal",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    assert mode == "brake_ramp_in"
    assert data["outdoor_temp"] < fake_temp <= BRAKE_FAKE_TEMP


def test_precool_triggered_by_long_term_forecast():
    st = base_sensor_data()["summer_threshold"]
    trigger = st + PRECOOL_MARGIN
    forecast = ",".join([str(st - 1)] * 6 + [str(trigger)])
    hass = DummyHass({"input_text.hourly_forecast_temperatures": forecast})
    s = create_sensor(hass)
    data = base_sensor_data(
        outdoor_temp_forecast_entity="input_text.hourly_forecast_temperatures"
    )
    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "normal",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    assert mode == "brake_ramp_in"
    assert data["outdoor_temp"] < fake_temp <= BRAKE_FAKE_TEMP


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
    s = create_sensor()
    data = base_sensor_data(
        indoor_temp=30.0,
        target_temp=20.0,
        outdoor_temp=5.0,
        aggressiveness=5.0,
    )
    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "normal",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )

    assert fake_temp <= BRAKE_FAKE_TEMP
    assert mode == "brake_ramp_in"
    assert data["outdoor_temp"] < fake_temp


def test_brake_temp_uses_offset_below_five_degrees():
    s = create_sensor()
    data = base_sensor_data(
        indoor_temp=23.0,
        target_temp=21.0,
        outdoor_temp=WINTER_BRAKE_THRESHOLD - 1.0,
        aggressiveness=1.0,
    )

    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "normal",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )

    assert mode == "brake_ramp_in"
    assert data["outdoor_temp"] < fake_temp < data["outdoor_temp"] + WINTER_BRAKE_TEMP_OFFSET


def test_brake_temp_caps_to_brake_fake_temp_above_five_degrees():
    s = create_sensor()
    data = base_sensor_data(
        indoor_temp=23.0,
        target_temp=21.0,
        outdoor_temp=WINTER_BRAKE_THRESHOLD + 1.0,
        aggressiveness=1.0,
    )

    fake_temp, mode, _ = s._calculate_output_temperature(
        data,
        "normal",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )

    assert mode == "brake_ramp_in"
    assert data["outdoor_temp"] < fake_temp <= BRAKE_FAKE_TEMP


def test_price_brake_consistent_across_temperatures():
    s = create_sensor()

    outdoor_temps = [-10.0, 0.0, 5.0, 10.0, 15.0, 17.0]

    for outdoor_temp in outdoor_temps:
        data = base_sensor_data(outdoor_temp=outdoor_temp)
        fake_temp, mode, _ = s._calculate_output_temperature(
            data,
            "expensive",
            0,
            datetime(2026, 1, 1, 0, 0),
            {},
        )

        assert mode == "brake_ramp_in", f"Mode should ramp in for outdoor_temp {outdoor_temp}"
        expected = (
            outdoor_temp + WINTER_BRAKE_TEMP_OFFSET
            if outdoor_temp < WINTER_BRAKE_THRESHOLD
            else BRAKE_FAKE_TEMP
        )
        assert outdoor_temp < fake_temp < expected


def test_price_brake_different_categories():
    s = create_sensor()
    data = base_sensor_data()

    expensive_categories = ["expensive", "very_expensive", "extreme"]

    for category in expensive_categories:
        fake_temp, mode, _ = s._calculate_output_temperature(
            data,
            category,
            0,
            datetime(2026, 1, 1, 0, 0),
            {},
        )

        assert mode == "brake_ramp_in", f"Mode should ramp in for {category}"
        expected = (
            data["outdoor_temp"] + WINTER_BRAKE_TEMP_OFFSET
            if data["outdoor_temp"] < WINTER_BRAKE_THRESHOLD
            else BRAKE_FAKE_TEMP
        )
        assert data["outdoor_temp"] < fake_temp < expected


def test_brake_ramp_reaches_full_brake_over_time():
    s = create_sensor()
    data = base_sensor_data()
    start = datetime(2026, 1, 1, 0, 0)
    _, mode_start, dbg_start = s._calculate_output_temperature(data, "expensive", 0, start, {})
    _, mode_end, dbg_end = s._calculate_output_temperature(
        data,
        "expensive",
        0,
        start + timedelta(minutes=15),
        {},
    )
    assert mode_start == "brake_ramp_in"
    assert dbg_start["brake_factor"] < 1.0
    assert mode_end == "full_brake"
    assert dbg_end["brake_factor"] == 1.0
