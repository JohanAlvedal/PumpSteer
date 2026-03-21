import sys
from datetime import datetime, timedelta
from pathlib import Path

from custom_components.pumpsteer.sensor import sensor
from custom_components.pumpsteer.temp_control_logic import calculate_temperature_output
from custom_components.pumpsteer.settings import (
    BRAKE_FAKE_TEMP,
    HEATING_COMPENSATION_FACTOR,
    MAX_FAKE_TEMP,
    MIN_FAKE_TEMP,
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
    assert fake_temp < data["outdoor_temp"]


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
    assert mode == "precool"
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
    assert mode == "precool"
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

    assert mode == "pid"
    assert fake_temp > data["outdoor_temp"]


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

    assert mode == "pid"
    assert fake_temp > data["outdoor_temp"]


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

    assert mode == "pid"
    assert fake_temp > data["outdoor_temp"]


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


def test_summer_mode_resets_pid_state():
    s = create_sensor()
    t0 = datetime(2026, 1, 1, 0, 0)

    # First tick in winter mode builds integral state.
    winter_data = base_sensor_data(indoor_temp=19.0, target_temp=21.0, outdoor_temp=5.0)
    _, winter_mode, winter_debug = s._calculate_output_temperature(
        winter_data,
        "normal",
        0,
        t0,
        {},
    )
    assert winter_mode == "pid"
    assert winter_debug["pid_integral"] > 0.0

    # Entering summer mode must flush PID memory.
    summer_data = base_sensor_data(outdoor_temp=20.0, summer_threshold=18.0)
    _, summer_mode, summer_debug = s._calculate_output_temperature(
        summer_data,
        "normal",
        0,
        t0 + timedelta(minutes=5),
        {},
    )
    assert summer_mode == "summer_mode"
    assert summer_debug["pid_integral"] == 0.0

    # Leaving summer mode should start from clean integral state.
    back_to_winter = base_sensor_data(indoor_temp=20.0, target_temp=21.0, outdoor_temp=5.0)
    _, _, back_debug = s._calculate_output_temperature(
        back_to_winter,
        "normal",
        0,
        t0 + timedelta(minutes=10),
        {},
    )
    assert round(back_debug["pid_integral"], 6) == 5.0


def test_brake_ramp_out_mode_after_request_removed():
    s = create_sensor()
    data = base_sensor_data()
    start = datetime(2026, 1, 1, 0, 0)

    # Ramp in to full brake.
    s._calculate_output_temperature(data, "expensive", 0, start, {})
    _, mode_full, dbg_full = s._calculate_output_temperature(
        data,
        "expensive",
        0,
        start + timedelta(minutes=15),
        {},
    )
    assert mode_full == "full_brake"
    assert dbg_full["brake_factor"] == 1.0

    # Remove brake request -> should ramp out first.
    _, mode_out, dbg_out = s._calculate_output_temperature(
        data,
        "normal",
        0,
        start + timedelta(minutes=16),
        {},
    )
    assert mode_out == "brake_ramp_out"
    assert 0.0 < dbg_out["brake_factor"] < 1.0


def test_dynamic_fake_temp_saturation_limits_pid_offset():
    s = create_sensor()
    t0 = datetime(2026, 1, 1, 0, 0)
    data = base_sensor_data(
        indoor_temp=10.0,
        target_temp=35.0,
        outdoor_temp=MIN_FAKE_TEMP + 0.2,
        aggressiveness=5.0,
        summer_threshold=30.0,
    )
    fake_temp, mode, debug = s._calculate_output_temperature(
        data,
        "normal",
        0,
        t0,
        {"pid_output_clamp": 12.0},
    )
    assert mode == "pid"
    assert fake_temp == MIN_FAKE_TEMP
    assert round(debug["pid_output"], 6) == round(MIN_FAKE_TEMP - data["outdoor_temp"], 6)


def test_aggressiveness_does_not_scale_pi_output_strength():
    t0 = datetime(2026, 1, 1, 0, 0)
    data_low = base_sensor_data(indoor_temp=20.0, target_temp=21.0, aggressiveness=0.0)
    data_high = base_sensor_data(indoor_temp=20.0, target_temp=21.0, aggressiveness=5.0)

    s_low = create_sensor()
    s_high = create_sensor()
    fake_low, mode_low, debug_low = s_low._calculate_output_temperature(
        data_low,
        "normal",
        0,
        t0,
        {},
    )
    fake_high, mode_high, debug_high = s_high._calculate_output_temperature(
        data_high,
        "normal",
        0,
        t0,
        {},
    )

    assert mode_low == "pid"
    assert mode_high == "pid"
    assert debug_high["pid_output"] == debug_low["pid_output"]
    assert fake_high == fake_low


def test_aggressiveness_zero_disables_price_brake():
    s = create_sensor()
    data = base_sensor_data(aggressiveness=0.0)
    fake_temp, mode, debug = s._calculate_output_temperature(
        data,
        "very_expensive",
        0,
        datetime(2026, 1, 1, 0, 0),
        {},
    )
    assert mode == "pid"
    assert debug["brake_requested"] is False
    assert fake_temp > data["outdoor_temp"]


def test_unified_pi_controller_architecture_is_active():
    s = create_sensor()
    assert hasattr(s, "_pi_controller")
    assert not hasattr(s, "_pid_integral")


def test_price_feedforward_affects_output_without_temp_error():
    s = create_sensor()
    data = base_sensor_data(indoor_temp=21.0, target_temp=21.0)
    t0 = datetime(2026, 1, 1, 0, 0)
    fake_cheap, _, _ = s._calculate_output_temperature(data, "very_cheap", 0, t0, {})
    fake_expensive, _, _ = s._calculate_output_temperature(
        data,
        "very_expensive",
        0,
        t0 + timedelta(minutes=1),
        {},
    )
    assert fake_cheap < data["outdoor_temp"]
    assert fake_expensive > data["outdoor_temp"]


def test_forecast_feedforward_is_continuous_not_binary_only():
    s = create_sensor()
    warm_bias = s._calculate_forecast_feedforward("15,17,19,21,22,23", 10.0, 18.0)
    cold_bias = s._calculate_forecast_feedforward("10,9,8,7,6,5", 10.0, 18.0)
    assert warm_bias > 0.0
    assert cold_bias < 0.0
