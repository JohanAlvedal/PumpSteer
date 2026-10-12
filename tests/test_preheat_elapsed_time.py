"""Preheat ramp timing through real offline control cycles."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.sensor import PumpSteerSensor


def _sensor(monkeypatch, holiday=False):
    prices = [1.0] * 96
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
    from custom_components.pumpsteer import holiday as holiday_module

    registry = SimpleNamespace(
        async_get_entity_id=lambda platform, domain, unique_id: (
            "switch.holiday" if unique_id.endswith("_holiday_mode") else None
        )
    )
    monkeypatch.setattr(holiday_module.er, "async_get", lambda hass: registry)
    entry = SimpleNamespace(
        entry_id="preheat-clock-test",
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
    sensor = PumpSteerSensor(
        SimpleNamespace(states=SimpleNamespace(get=states.get)), entry
    )

    async def cold_forecast():
        return [0.0] * 6

    monkeypatch.setattr(sensor, "_forecast_temps", cold_forecast)
    return sensor, states


def _cycle(sensor, monkeypatch, seconds):
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)
    asyncio.run(sensor._do_update())
    return sensor.extra_state_attributes


@pytest.mark.parametrize(
    "seconds",
    [
        list(range(0, 601, 30)),
        list(range(0, 601, 60)),
        list(range(0, 601, 120)),
        [0, 30, 75, 240, 300, 420, 600],
    ],
    ids=["30s", "60s", "120s", "irregular"],
)
@pytest.mark.parametrize("holiday", [False, True])
def test_poll_intervals_give_same_elapsed_preheat_factor(monkeypatch, seconds, holiday):
    sensor, _ = _sensor(monkeypatch, holiday=holiday)
    for elapsed in seconds:
        sample = _cycle(sensor, monkeypatch, elapsed)
        assert sample["mode"] == "preheating"
    # Initial nominal minute + ten elapsed minutes, with a 15-minute ramp.
    assert sensor._preheat_ramp == pytest.approx(11 / 15)


def test_duplicate_and_backwards_timestamps_do_not_add_preheat(monkeypatch):
    sensor, _ = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    initial = sensor._preheat_ramp
    for elapsed in (0, -60, 0):
        _cycle(sensor, monkeypatch, elapsed)
        assert sensor._preheat_ramp == initial
    _cycle(sensor, monkeypatch, 60)
    assert sensor._preheat_ramp == pytest.approx(2 / 15)


def test_long_poll_gap_is_bounded_to_five_minutes(monkeypatch):
    sensor, _ = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    assert _cycle(sensor, monkeypatch, 20 * 60)["mode"] == "preheating"
    assert sensor._preheat_ramp == pytest.approx(6 / 15)


def test_normal_ramp_out_uses_elapsed_time(monkeypatch):
    sensor, states = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    _cycle(sensor, monkeypatch, 120)
    states["sensor.price"].attributes["today"][:] = [1.0] * 96
    sample = _cycle(sensor, monkeypatch, 180)
    assert sample["mode"] == "normal"
    assert sensor._preheat_ramp == pytest.approx(2 / 15)
    _cycle(sensor, monkeypatch, 300)
    assert sensor._preheat_ramp == pytest.approx(0.0)


@pytest.mark.parametrize("interruption", ["pre_braking", "braking", "precool"])
def test_other_modes_do_not_charge_inactive_time(monkeypatch, interruption):
    sensor, states = _sensor(monkeypatch)
    _cycle(sensor, monkeypatch, 0)
    factor = sensor._preheat_ramp
    if interruption == "braking":
        states["sensor.price"].attributes["today"][32:34] = [10.0] * 2
    elif interruption == "pre_braking":
        states["sensor.price"].attributes["today"][33:35] = [10.0] * 2
    else:

        async def warm_forecast():
            return [25.0] * 6

        monkeypatch.setattr(sensor, "_forecast_temps", warm_forecast)
    # One pre-brake cycle isolates this clock test from the separately tested
    # upstream provenance defect on the second consecutive pre-brake cycle.
    times = (180,) if interruption == "pre_braking" else (60, 120, 180)
    for elapsed in times:
        assert _cycle(sensor, monkeypatch, elapsed)["mode"] == interruption
        assert sensor._preheat_ramp == factor
    states["sensor.price"].attributes["today"][:] = [1.0] * 96
    states["sensor.price"].attributes["today"][40:42] = [10.0] * 2

    async def cold_forecast():
        return [0.0] * 6

    monkeypatch.setattr(sensor, "_forecast_temps", cold_forecast)
    assert _cycle(sensor, monkeypatch, 240)["mode"] == "preheating"
    assert sensor._preheat_ramp == pytest.approx(2 / 15)


@pytest.mark.parametrize("reset", ["safe", "summer", "aggressiveness_zero"])
def test_reset_starts_with_one_nominal_step(monkeypatch, reset):
    sensor, states = _sensor(monkeypatch)
    for elapsed in (0, 60, 120):
        _cycle(sensor, monkeypatch, elapsed)
    if reset == "safe":
        states["sensor.indoor"].state = "unavailable"
    elif reset == "summer":
        states["sensor.outdoor"].state = "19"
    else:
        sensor._config_entry.options["aggressiveness"] = 0
    _cycle(sensor, monkeypatch, 180)
    assert sensor._preheat_ramp == 0.0
    states["sensor.indoor"].state = "20.5"
    states["sensor.outdoor"].state = "5"
    sensor._config_entry.options["aggressiveness"] = 3
    assert _cycle(sensor, monkeypatch, 900)["mode"] == "preheating"
    assert sensor._preheat_ramp == pytest.approx(1 / 15)


def test_restart_starts_with_one_nominal_step(monkeypatch):
    previous, _ = _sensor(monkeypatch)
    for elapsed in (0, 60, 120):
        _cycle(previous, monkeypatch, elapsed)
    restarted, _ = _sensor(monkeypatch)
    restarted._attributes = previous.extra_state_attributes
    _cycle(restarted, monkeypatch, 600)
    assert restarted._preheat_ramp == pytest.approx(1 / 15)


def test_repeated_dst_hour_uses_elapsed_time(monkeypatch):
    sensor, states = _sensor(monkeypatch)
    prices = [1.0] * 100
    prices[20:22] = [10.0] * 2
    states["sensor.price"].attributes["today"] = prices
    for fold in (0, 1):
        now = datetime(
            2026, 10, 25, 2, 15, tzinfo=ZoneInfo("Europe/Stockholm"), fold=fold
        )
        monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)
        asyncio.run(sensor._do_update())
        assert sensor.extra_state_attributes["mode"] == "preheating"
    # One real hour elapsed despite equal wall-clock readings; the gap is capped.
    assert sensor._preheat_ramp == pytest.approx(6 / 15)
