"""PI memory must not wind up behind an active price brake overlay."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.sensor import PumpSteerSensor


@pytest.fixture(params=[False, True], ids=["normal_target", "holiday_target"])
def setup_sensor(monkeypatch, request):
    holiday = request.param
    prices = [1.0] * 96
    prices[32:34] = [10.0] * 2
    prices[35:37] = [10.0] * 2
    states = {
        "sensor.indoor": SimpleNamespace(
            state="15.5" if holiday else "20.5", attributes={}
        ),
        "sensor.outdoor": SimpleNamespace(state="5", attributes={}),
        "sensor.price": SimpleNamespace(state="1", attributes={"today": prices}),
        "switch.holiday": SimpleNamespace(
            state="on" if holiday else "off", attributes={}
        ),
    }
    registry = SimpleNamespace(
        async_get_entity_id=lambda platform, domain, unique_id: (
            "switch.holiday" if unique_id.endswith("_holiday_mode") else None
        )
    )
    from custom_components.pumpsteer import holiday as holiday_module

    monkeypatch.setattr(holiday_module.er, "async_get", lambda hass: registry)
    entry = SimpleNamespace(
        entry_id="integral-test",
        data={},
        options={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "electricity_price_entity": "sensor.price",
            "target_temperature": 21,
            "summer_threshold": 18,
            "aggressiveness": 3,
            "house_inertia": 2,
            "preheat_boost_enabled": False,
        },
    )
    return PumpSteerSensor(
        SimpleNamespace(states=SimpleNamespace(get=states.get)), entry
    ), states


def _cycle(sensor, monkeypatch, minute):
    now = datetime(2026, 10, 11, 7, tzinfo=timezone.utc) + timedelta(minutes=minute)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)
    asyncio.run(sensor._do_update())
    return sensor.extra_state_attributes


def _start_braking(sensor, monkeypatch):
    _cycle(sensor, monkeypatch, 0)
    integral = sensor._pi._integral
    assert integral > 0.0
    for minute in (60, 61, 62):
        sample = _cycle(sensor, monkeypatch, minute)
        assert sample["mode"] == "braking"
        assert sensor._pi._integral == integral
    return integral


def test_integral_frozen_during_successive_hold_cycles(setup_sensor, monkeypatch):
    sensor, _ = setup_sensor
    integral = _start_braking(sensor, monkeypatch)
    factor = sensor._brake_ramp
    for minute in (90, 91, 92):
        sample = _cycle(sensor, monkeypatch, minute)
        assert sample["brake_should_hold"] is True
        assert sensor._brake_ramp == factor
        assert sensor._pi._integral == integral
        assert sample["pi_i_term"] == round(integral, 3)


def test_integral_frozen_until_price_ramp_out_finishes(setup_sensor, monkeypatch):
    sensor, states = setup_sensor
    integral = _start_braking(sensor, monkeypatch)
    states["sensor.price"].attributes["today"][35:37] = [1.0] * 2
    for minute in (90, 91):
        sample = _cycle(sensor, monkeypatch, minute)
        assert sample["brake_should_hold"] is False
        assert sample["brake_factor"] > 0.0
        assert sensor._pi._integral == integral
    _cycle(sensor, monkeypatch, 92)
    _cycle(sensor, monkeypatch, 93)
    assert sensor._brake_ramp == 0.0
    assert sensor._pi._integral > integral


def test_comfort_floor_releases_hold_and_pi_resumes(setup_sensor, monkeypatch):
    sensor, states = setup_sensor
    integral = _start_braking(sensor, monkeypatch)
    states["sensor.indoor"].state = "10"
    previous_factor = sensor._brake_ramp
    for minute in (90, 91):
        sample = _cycle(sensor, monkeypatch, minute)
        assert sample["brake_should_hold"] is False
        assert 0.0 < sensor._brake_ramp < previous_factor
        previous_factor = sensor._brake_ramp
        assert sensor._pi._integral == integral
    _cycle(sensor, monkeypatch, 92)
    _cycle(sensor, monkeypatch, 93)
    assert sensor._brake_ramp == 0.0
    assert sensor._pi._integral > integral


def test_unrestricted_pi_still_integrates(setup_sensor, monkeypatch):
    sensor, _ = setup_sensor
    values = []
    for minute in (0, 1, 2):
        sample = _cycle(sensor, monkeypatch, minute)
        assert sample["brake_factor"] == 0.0
        values.append(sensor._pi._integral)
    assert 0.0 < values[0] < values[1] < values[2]
