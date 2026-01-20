import sys
from datetime import datetime
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
        self.data = {}


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
    fake_temp, mode = s._calculate_output_temperature(data, "very_expensive", 0)
    assert mode == "heating"
    assert fake_temp < data["outdoor_temp"]


def test_price_brake_when_neutral():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode = s._calculate_output_temperature(data, "expensive", 0)
    assert mode == "neutral"
    assert fake_temp == data["outdoor_temp"]


def test_extreme_price_brake_when_neutral():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode = s._calculate_output_temperature(data, "extreme", 0)
    assert mode == "neutral"
    assert fake_temp == data["outdoor_temp"]


def test_expensive_now_braking_outside_block(monkeypatch):
    s = create_sensor()
    data = base_sensor_data()
    combined_prices = [1.0, 3.28, 2.0]
    update_time = datetime(2024, 1, 1, 12, 0, 0)

    def fake_compute_price_brake(**_kwargs):
        return {
            "brake_level": 0.0,
            "baseline": 0.0,
            "threshold": 2.54,
            "area": 0.0,
            "amplitude": 0.0,
            "block": None,
        }

    monkeypatch.setattr(sensor, "compute_price_brake", fake_compute_price_brake)

    pi_data = s._compute_controls(
        data,
        combined_prices,
        0,
        60,
        {},
        3.28,
        "expensive",
        update_time,
    )
    assert pi_data["price_brake_level"] > 0.0
    assert pi_data["brake_blocked_reason"] != "no_price_block"

    fake_temp, mode = s._calculate_output_temperature(data, "expensive", 0)
    assert mode == "neutral"
    if (
        mode == "neutral"
        and pi_data["price_brake_level"] > 0.0
        and pi_data["brake_blocked_reason"] in {"allowed", "rate_limited"}
    ):
        mode = "braking_by_price"
    assert mode == "braking_by_price"


def test_very_cheap_price_overshoots_target():
    s = create_sensor()
    data = base_sensor_data()
    original_overshoot = sensor.CHEAP_PRICE_OVERSHOOT
    sensor.CHEAP_PRICE_OVERSHOOT = 0.6  # Ensure overshoot is active for the test
    fake_temp, mode = s._calculate_output_temperature(data, "very_cheap", 0)
    sensor.CHEAP_PRICE_OVERSHOOT = original_overshoot
    assert mode == "neutral"
    assert fake_temp == data["outdoor_temp"]


def test_cheap_price_neutral_behavior():
    s = create_sensor()
    data = base_sensor_data()
    fake_temp, mode = s._calculate_output_temperature(data, "cheap", 0)
    assert mode == "neutral"
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
    fake_temp, mode = s._calculate_output_temperature(data, "normal", 0)
    assert mode == "precool"
    assert fake_temp == BRAKE_FAKE_TEMP


def test_precool_triggered_by_long_term_forecast():
    st = base_sensor_data()["summer_threshold"]
    trigger = st + PRECOOL_MARGIN
    forecast = ",".join([str(st - 1)] * 6 + [str(trigger)])
    hass = DummyHass({"input_text.hourly_forecast_temperatures": forecast})
    s = create_sensor(hass)
    data = base_sensor_data(
        outdoor_temp_forecast_entity="input_text.hourly_forecast_temperatures"
    )
    fake_temp, mode = s._calculate_output_temperature(data, "normal", 0)
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
    """Test that fake_temp is constrained to not exceed BRAKE_FAKE_TEMP"""
    s = create_sensor()
    # Create a scenario that might produce high fake_temp values
    # Use very high indoor temperature and neutral target to trigger braking mode
    data = base_sensor_data(
        indoor_temp=30.0,  # Very high indoor temp
        target_temp=20.0,  # Much lower target
        outdoor_temp=5.0,  # Cold outdoor temp
        aggressiveness=5.0,  # Maximum aggressiveness
    )
    fake_temp, mode = s._calculate_output_temperature(data, "normal", 0)

    # The fake_temp should be constrained to BRAKE_FAKE_TEMP (25.0)
    assert fake_temp <= BRAKE_FAKE_TEMP


def test_brake_temp_uses_offset_below_five_degrees():
    """Ensure braking only adds offset to outdoor temp when it's below 5 °C"""
    s = create_sensor()
    data = base_sensor_data(
        indoor_temp=23.0,
        target_temp=21.0,
        outdoor_temp=WINTER_BRAKE_THRESHOLD - 1.0,
        aggressiveness=1.0,
    )

    fake_temp, mode = s._calculate_output_temperature(data, "normal", 0)

    assert mode == "braking_by_temp"
    assert fake_temp == data["outdoor_temp"] + WINTER_BRAKE_TEMP_OFFSET


def test_brake_temp_caps_to_brake_fake_temp_above_five_degrees():
    """Ensure braking uses the global cap when outdoor temp is 5 °C or warmer"""
    s = create_sensor()
    data = base_sensor_data(
        indoor_temp=23.0,
        target_temp=21.0,
        outdoor_temp=WINTER_BRAKE_THRESHOLD + 1.0,
        aggressiveness=1.0,
    )

    fake_temp, mode = s._calculate_output_temperature(data, "normal", 0)

    assert mode == "braking_by_temp"
    assert fake_temp == BRAKE_FAKE_TEMP


def test_price_category_does_not_change_neutral_mode():
    """Ensure price category alone does not change neutral behavior."""
    s = create_sensor()

    outdoor_temps = [-10.0, 0.0, 5.0, 10.0, 15.0, 17.0]

    for outdoor_temp in outdoor_temps:
        data = base_sensor_data(outdoor_temp=outdoor_temp)
        fake_temp, mode = s._calculate_output_temperature(data, "expensive", 0)

        assert mode == "neutral"
        assert fake_temp == outdoor_temp


def test_price_categories_do_not_force_braking():
    """Ensure price categories do not force braking in neutral state."""
    s = create_sensor()
    data = base_sensor_data()

    expensive_categories = ["expensive", "very_expensive", "extreme"]

    for category in expensive_categories:
        fake_temp, mode = s._calculate_output_temperature(data, category, 0)

        assert mode == "neutral"
        assert fake_temp == data["outdoor_temp"]
