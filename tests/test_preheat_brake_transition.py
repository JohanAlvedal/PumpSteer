"""A preheat output ends the old brake phase instead of hiding its state."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.thermal_model import ThermalSample


def _sensor():
    prices = [1.0] * 96
    prices[32:34] = [10.0] * 2
    states = {
        "sensor.indoor": SimpleNamespace(state="20.5", attributes={}),
        "sensor.outdoor": SimpleNamespace(state="5", attributes={}),
        "sensor.price": SimpleNamespace(state="1", attributes={"today": prices}),
    }
    entry = SimpleNamespace(
        entry_id="preheat-brake-test",
        data={},
        options={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "electricity_price_entity": "sensor.price",
            "target_temperature": 21,
            "summer_threshold": 18,
            "aggressiveness": 3,
            "house_inertia": 2,
            "preheat_boost_enabled": True,
        },
    )
    return PumpSteerSensor(
        SimpleNamespace(states=SimpleNamespace(get=states.get)), entry
    ), states


def _cycle(sensor, monkeypatch, minute, forecast=None):
    now = datetime(2026, 10, 11, 7, tzinfo=timezone.utc) + timedelta(minutes=minute)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)

    async def temperatures():
        return forecast

    monkeypatch.setattr(sensor, "_forecast_temps", temperatures)
    asyncio.run(sensor._do_update())
    return sensor.extra_state_attributes


def _actual_brake(sensor, monkeypatch):
    for minute in (60, 61, 62):
        assert _cycle(sensor, monkeypatch, minute)["mode"] == "braking"


def _next_price_block(states):
    prices = states["sensor.price"].attributes["today"]
    prices[:] = [1.0] * 96
    prices[40:42] = [10.0] * 2


@pytest.mark.parametrize("previous_phase", ["braking", "pre_braking", "precool"])
def test_preheat_ends_internal_brake_state(monkeypatch, previous_phase):
    sensor, states = _sensor()
    if previous_phase == "braking":
        _actual_brake(sensor, monkeypatch)
    elif previous_phase == "pre_braking":
        assert _cycle(sensor, monkeypatch, 45)["mode"] == previous_phase
    else:
        assert _cycle(sensor, monkeypatch, 0, [25.0] * 6)["mode"] == previous_phase
    assert sensor._brake_ramp > 0.0
    _next_price_block(states)

    sample = _cycle(sensor, monkeypatch, 90, [0.0] * 6)

    assert sample["mode"] == "preheating"
    assert sample["brake_factor"] == 0.0
    assert sensor._brake_ramp == 0.0
    assert sensor._brake_last_t is None
    assert sensor._brake_last_expensive_t is None
    assert sensor._was_braking_last_cycle is False


def test_preheat_interruption_cannot_later_revive_an_old_price_brake(monkeypatch):
    sensor, states = _sensor()
    _actual_brake(sensor, monkeypatch)
    _next_price_block(states)
    for minute in (90, 120, 160):
        sample = _cycle(sensor, monkeypatch, minute, [0.0] * 6)
        assert sample["mode"] == "preheating"
        assert sample["brake_factor"] == 0.0


def test_real_short_dip_keeps_its_brake_even_with_a_cold_forecast(monkeypatch):
    sensor, states = _sensor()
    states["sensor.price"].attributes["today"][35:37] = [10.0] * 2
    _actual_brake(sensor, monkeypatch)
    factor = sensor._brake_ramp

    sample = _cycle(sensor, monkeypatch, 90, [0.0] * 6)

    assert sample["mode"] == "brake_hold"
    assert sample["bridge_short_dip"] is True
    assert sensor._brake_ramp == factor
    assert sensor._was_braking_last_cycle is True


@pytest.mark.parametrize("blocked_by", ["disabled", "headroom"])
def test_brake_still_ramps_out_when_preheat_does_not_take_over(monkeypatch, blocked_by):
    sensor, states = _sensor()
    _actual_brake(sensor, monkeypatch)
    _next_price_block(states)
    before = sensor._brake_ramp
    if blocked_by == "disabled":
        sensor._config_entry.options["preheat_boost_enabled"] = False
    else:
        states["sensor.indoor"].state = "22"

    sample = _cycle(sensor, monkeypatch, 63, [0.0] * 6)

    assert sample["mode"] == "normal"
    assert 0.0 < sensor._brake_ramp < before
    assert sensor._was_braking_last_cycle is True


@pytest.mark.parametrize("pending", [19, 20])
def test_preheat_finishes_thermal_phase_using_the_existing_sample_threshold(
    monkeypatch, pending
):
    sensor, states = _sensor()
    _actual_brake(sensor, monkeypatch)
    _next_price_block(states)
    sensor._thermal_model._samples = [ThermalSample(20.5, 5.0, -0.775)] * pending

    assert _cycle(sensor, monkeypatch, 90, [0.0] * 6)["mode"] == "preheating"

    assert sensor._was_braking_last_cycle is False
    assert sensor._thermal_model.sample_count == (20 if pending == 20 else 0)
    assert sensor._thermal_model.pending_samples == (0 if pending == 20 else 19)
    # Another preheat cycle must not finish a second phase or lose partial samples.
    _cycle(sensor, monkeypatch, 91, [0.0] * 6)
    assert sensor._thermal_model.sample_count == (20 if pending == 20 else 0)
    assert sensor._thermal_model.pending_samples == (0 if pending == 20 else 19)


def test_precool_without_a_price_brake_does_not_trigger_a_thermal_fit(monkeypatch):
    sensor, states = _sensor()
    assert _cycle(sensor, monkeypatch, 0, [25.0] * 6)["mode"] == "precool"
    _next_price_block(states)
    sensor._thermal_model._samples = [ThermalSample(20.5, 5.0, -0.775)] * 20

    assert _cycle(sensor, monkeypatch, 90, [0.0] * 6)["mode"] == "preheating"

    assert sensor._thermal_model.is_valid is False
    assert sensor._thermal_model.pending_samples == 20


def test_preheat_does_not_persist_a_hidden_brake(monkeypatch):
    sensor, states = _sensor()
    _actual_brake(sensor, monkeypatch)
    _next_price_block(states)
    _cycle(sensor, monkeypatch, 90, [0.0] * 6)
    restore_module = __import__(
        "homeassistant.helpers.restore_state", fromlist=["ExtraStoredData"]
    )
    monkeypatch.setattr(restore_module, "ExtraStoredData", object, raising=False)

    saved = sensor.extra_restore_state_data.as_dict()

    assert saved["brake_ramp"] == 0.0
    assert saved["brake_last_t"] is None
    assert saved["brake_last_expensive_t"] is None
    # This key is added by the independent brake-provenance fix.
    assert saved.get("was_braking_last_cycle", False) is False


def test_the_next_price_phase_starts_with_a_fresh_brake_ramp(monkeypatch):
    sensor, states = _sensor()
    _actual_brake(sensor, monkeypatch)
    _next_price_block(states)
    assert _cycle(sensor, monkeypatch, 90, [0.0] * 6)["mode"] == "preheating"

    sample = _cycle(sensor, monkeypatch, 165, [0.0] * 6)

    assert sample["mode"] == "pre_braking"
    assert sensor._brake_ramp == pytest.approx(1 / 15)
    assert _cycle(sensor, monkeypatch, 180)["mode"] == "braking"
    assert sensor._brake_ramp == pytest.approx(2 / 15)
    assert sensor._was_braking_last_cycle is True
