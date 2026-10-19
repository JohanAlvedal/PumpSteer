"""A price-dip bridge needs an observed expensive braking phase."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.sensor import (
    MODE_BRAKE_HOLD,
    MODE_BRAKING,
    MODE_PREBRAKE,
    PumpSteerSensor,
)


def _sensor():
    prices = [1.0] * 96
    prices[33:35] = [10.0] * 2
    prices[36:38] = [10.0] * 2
    states = {
        "sensor.indoor": SimpleNamespace(state="20.5", attributes={}),
        "sensor.outdoor": SimpleNamespace(state="5", attributes={}),
        "sensor.price": SimpleNamespace(state="1", attributes={"today": prices}),
    }
    entry = SimpleNamespace(
        entry_id="provenance-test",
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
        add_update_listener=lambda callback: lambda: None,
    )
    hass = SimpleNamespace(
        states=SimpleNamespace(get=states.get),
        bus=SimpleNamespace(async_listen_once=lambda event, callback: None),
        is_running=False,
    )
    return PumpSteerSensor(hass, entry), states


def _cycle(sensor, monkeypatch, minute):
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc) + timedelta(minutes=minute)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)
    # Each cycle supplies new HA reports, including after entity restoration.
    for key in ("indoor_temp_entity", "real_outdoor_entity"):
        sensor.hass.states.get(sensor._cfg()[key]).last_reported = now
    asyncio.run(sensor._do_update())
    return sensor.extra_state_attributes


def test_prebrake_keeps_ramping_until_actual_expensive_phase(monkeypatch):
    sensor, _ = _sensor()
    samples = [_cycle(sensor, monkeypatch, minute) for minute in (10, 11, 12)]
    assert [sample["mode"] for sample in samples] == [MODE_PREBRAKE] * 3
    assert [sample["brake_factor"] for sample in samples] == [0.067, 0.133, 0.2]


def test_actual_expensive_phase_allows_flat_bridge(monkeypatch):
    sensor, _ = _sensor()
    for minute in (15, 16, 17):
        assert _cycle(sensor, monkeypatch, minute)["mode"] == MODE_BRAKING
    factor = sensor._brake_ramp
    for minute in (45, 46, 47):
        sample = _cycle(sensor, monkeypatch, minute)
        assert sample["mode"] == MODE_BRAKE_HOLD
        assert sensor._brake_ramp == factor


def test_precool_is_not_proof_of_expensive_braking(monkeypatch):
    sensor, _ = _sensor()

    async def warm_forecast():
        return [25.0] * 6

    monkeypatch.setattr(sensor, "_forecast_temps", warm_forecast)
    assert _cycle(sensor, monkeypatch, 0)["mode"] == "precool"

    async def no_forecast():
        return None

    monkeypatch.setattr(sensor, "_forecast_temps", no_forecast)
    assert _cycle(sensor, monkeypatch, 10)["mode"] == MODE_PREBRAKE


@pytest.mark.parametrize("reset", ["safe", "summer", "aggressiveness_zero"])
def test_reset_forgets_price_braking_provenance(monkeypatch, reset):
    sensor, states = _sensor()
    _cycle(sensor, monkeypatch, 15)
    if reset == "safe":
        states["sensor.indoor"].state = "unavailable"
    elif reset == "summer":
        states["sensor.outdoor"].state = "19"
    else:
        sensor._config_entry.options["aggressiveness"] = 0
    _cycle(sensor, monkeypatch, 16)
    states["sensor.indoor"].state = "20.5"
    states["sensor.outdoor"].state = "5"
    sensor._config_entry.options["aggressiveness"] = 3
    assert _cycle(sensor, monkeypatch, 50)["mode"] == MODE_PREBRAKE


@pytest.mark.parametrize("actual_expensive", [False, True])
def test_brake_provenance_survives_restore(monkeypatch, actual_expensive):
    sensor, _ = _sensor()
    _cycle(sensor, monkeypatch, 15 if actual_expensive else 10)
    restore_module = __import__(
        "homeassistant.helpers.restore_state", fromlist=["ExtraStoredData"]
    )
    monkeypatch.setattr(restore_module, "ExtraStoredData", object, raising=False)
    saved = sensor.extra_restore_state_data.as_dict()
    assert saved["was_braking_last_cycle"] is actual_expensive
    restored, _ = _sensor()

    async def extra_data():
        return SimpleNamespace(as_dict=lambda: saved)

    monkeypatch.setattr(
        restored, "async_get_last_extra_data", extra_data, raising=False
    )
    asyncio.run(restored.async_added_to_hass())
    sample = _cycle(restored, monkeypatch, 45 if actual_expensive else 11)
    assert sample["mode"] == (MODE_BRAKE_HOLD if actual_expensive else MODE_PREBRAKE)


@pytest.mark.parametrize("untrusted", [None, "true", 1, False])
def test_legacy_or_untrusted_restore_does_not_invent_provenance(monkeypatch, untrusted):
    sensor, _ = _sensor()
    now = datetime(2026, 10, 11, 8, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)
    saved = {
        "brake_ramp": 0.5,
        "brake_last_t": now.isoformat(),
        "brake_last_expensive_t": now.isoformat(),
    }
    if untrusted is not None:
        saved["was_braking_last_cycle"] = untrusted

    async def extra_data():
        return SimpleNamespace(as_dict=lambda: saved)

    monkeypatch.setattr(sensor, "async_get_last_extra_data", extra_data, raising=False)
    asyncio.run(sensor.async_added_to_hass())
    assert _cycle(sensor, monkeypatch, 11)["mode"] == MODE_PREBRAKE
