"""Keep PI memory, without integrating the interval spent in precool."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.sensor import PumpSteerSensor


def _sensor(monkeypatch, holiday=False, aggressiveness=3):
    target = sensor_module.HOLIDAY_TEMP if holiday else 21.0
    states = {
        "sensor.indoor": SimpleNamespace(state=str(target - 0.5), attributes={}),
        "sensor.outdoor": SimpleNamespace(state="5", attributes={}),
        "sensor.price": SimpleNamespace(state="1", attributes={"today": [1.0] * 96}),
    }
    entry = SimpleNamespace(
        entry_id="precool-clock-test",
        data={},
        options={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "electricity_price_entity": "sensor.price",
            "target_temperature": 21,
            "summer_threshold": 18,
            "aggressiveness": aggressiveness,
            "house_inertia": 2,
        },
    )

    async def holiday_mode(*args):
        return holiday

    monkeypatch.setattr(sensor_module, "async_update_holiday", holiday_mode)
    return PumpSteerSensor(
        SimpleNamespace(states=SimpleNamespace(get=states.get)), entry
    ), states


def _time(minute):
    return datetime(2026, 10, 11, 7, tzinfo=timezone.utc) + timedelta(minutes=minute)


def _cycle(sensor, monkeypatch, minute, forecast=None):
    now = _time(minute)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)

    async def temperatures():
        return forecast

    monkeypatch.setattr(sensor, "_forecast_temps", temperatures)
    asyncio.run(sensor._do_update())
    return sensor.extra_state_attributes


@pytest.mark.parametrize("warm_updates", [(0.5,), (0.5, 0.6), (0.5, 0.5, 0.6)])
@pytest.mark.parametrize("holiday", [False, True])
@pytest.mark.parametrize("aggressiveness", [0, 3])
def test_precool_and_first_resume_preserve_integral_then_normal_pi_resumes(
    monkeypatch, warm_updates, holiday, aggressiveness
):
    sensor, _ = _sensor(monkeypatch, holiday, aggressiveness)
    _cycle(sensor, monkeypatch, 0)
    integral = sensor._pi._integral
    assert integral > 0.0
    for minute in warm_updates:
        sample = _cycle(sensor, monkeypatch, minute, [25.0] * 6)
        assert sample["mode"] == "precool"
        assert sample["fake_outdoor_temperature"] >= 5.0
        assert sample["pi_i_term"] is None
        assert sensor._pi._integral == integral
        assert sensor._pi._last_time == _time(minute)

    sample = _cycle(sensor, monkeypatch, 30)

    assert sample["mode"] == ("holiday" if holiday and aggressiveness else "normal")
    if aggressiveness:
        assert sensor._brake_ramp == 0.0
    assert sensor._pi._integral == integral
    assert sensor._pi._last_time == _time(30)
    _cycle(sensor, monkeypatch, 31)
    assert sensor._pi._integral == pytest.approx(integral + sensor_module.PID_KI * 0.5)


def test_starting_in_precool_does_not_bootstrap_an_integral(monkeypatch):
    sensor, _ = _sensor(monkeypatch)
    assert _cycle(sensor, monkeypatch, 0.5, [25.0] * 6)["mode"] == "precool"
    assert sensor._pi._integral == 0.0
    _cycle(sensor, monkeypatch, 30)
    assert sensor._pi._integral == 0.0
    _cycle(sensor, monkeypatch, 31)
    assert sensor._pi._integral == pytest.approx(sensor_module.PID_KI * 0.5)


def test_unrestricted_pi_still_integrates_its_actual_elapsed_time(monkeypatch):
    sensor, _ = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    integral = sensor._pi._integral
    _cycle(sensor, monkeypatch, 30)
    assert sensor._pi._integral == pytest.approx(
        integral + sensor_module.PID_KI * 0.5 * 30
    )


def test_first_preheat_after_precool_skips_catch_up_then_integrates_normally(
    monkeypatch,
):
    sensor, states = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    integral = sensor._pi._integral
    _cycle(sensor, monkeypatch, 0.5, [25.0] * 6)
    states["sensor.price"].attributes["today"][40:42] = [10.0] * 2

    assert _cycle(sensor, monkeypatch, 30, [0.0] * 6)["mode"] == "preheating"
    assert sensor._pi._integral == integral
    _cycle(sensor, monkeypatch, 31, [0.0] * 6)
    assert sensor._pi._integral == pytest.approx(integral + sensor_module.PID_KI * 0.5)


@pytest.mark.parametrize(
    "reset_mode", ["summer_mode", "safe_mode", "aggressiveness_zero"]
)
def test_existing_reset_clears_the_precool_pause(monkeypatch, reset_mode):
    sensor, states = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    _cycle(sensor, monkeypatch, 0.5, [25.0] * 6)
    if reset_mode == "summer_mode":
        states["sensor.outdoor"].state = "19"
    elif reset_mode == "safe_mode":
        states["sensor.indoor"].state = "unavailable"
    else:
        sensor._config_entry.options["aggressiveness"] = 0
    _cycle(sensor, monkeypatch, 30)
    if reset_mode == "aggressiveness_zero":
        assert 0.0 < sensor._pi._integral < 0.001
    states["sensor.outdoor"].state = "5"
    states["sensor.indoor"].state = "20.5"

    _cycle(sensor, monkeypatch, 31)

    assert sensor._pi._integral > 0.0
    assert sensor._pi._integral < 0.1


def test_a_long_precool_phase_keeps_its_integral_through_the_first_resume(monkeypatch):
    sensor, _ = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    integral = sensor._pi._integral
    for minute in (0.5, 1.5, 30, 60):
        assert _cycle(sensor, monkeypatch, minute, [25.0] * 6)["mode"] == "precool"
        assert sensor._pi._integral == integral
        assert sensor._pi._last_time == _time(minute)

    _cycle(sensor, monkeypatch, 90)

    assert sensor._pi._integral == integral
    assert sensor._pi._last_time == _time(90)


def test_update_error_does_not_lose_a_pending_precool_pause(monkeypatch):
    sensor, _ = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    integral = sensor._pi._integral
    _cycle(sensor, monkeypatch, 0.5, [25.0] * 6)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: _time(30))

    async def broken_forecast():
        raise RuntimeError("synthetic forecast failure")

    monkeypatch.setattr(sensor, "_forecast_temps", broken_forecast)
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["status"] == "error"

    _cycle(sensor, monkeypatch, 31)

    assert sensor._brake_ramp == 0.0
    assert sensor._pi._integral == integral
    _cycle(sensor, monkeypatch, 32)
    assert sensor._pi._integral == pytest.approx(integral + sensor_module.PID_KI * 0.5)
