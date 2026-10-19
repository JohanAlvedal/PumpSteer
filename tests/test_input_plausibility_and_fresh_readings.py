"""Implausible readings never drive output; fresh valid readings keep control state."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_ohmigo_watchdog_safety import rig, update  # noqa: F401
from test_temperature_input_safety import control, setup_sensor  # noqa: F401

from custom_components.pumpsteer import relay_guard
from custom_components.pumpsteer.settings import MAX_FAKE_TEMP
from custom_components.pumpsteer.sensor import MODE_PI, MODE_SAFE, MODE_SUMMER


@pytest.fixture
def ctl(request):
    return request.getfixturevalue("control")


@pytest.fixture
def guarded(request):
    return request.getfixturevalue("rig")


def _pushed(sensor):
    return [c[2]["value"] for c in sensor.hass.services.calls if c[0] == "number"]


# ── B2: plausibility and output cap ──────────────────────────────────────────


@pytest.mark.parametrize("indoor", ["0", "-40", "4.9", "35.1", "85", "655.35"])
def test_implausible_indoor_enters_safe_mode_and_forwards_real_outdoor(ctl, indoor):
    sensor, states, _ = ctl
    states["sensor.indoor"].state = indoor
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_SAFE
    assert sensor._last_pi_result is None
    assert _pushed(sensor) == [-3.5]  # authentic outdoor passthrough only


@pytest.mark.parametrize("outdoor", ["-50.1", "45.1", "85", "-273"])
def test_implausible_outdoor_sends_nothing(ctl, outdoor):
    sensor, states, _ = ctl
    states["sensor.outdoor"].state = outdoor
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_SAFE
    assert sensor.state is None
    assert sensor.hass.services.calls == []


@pytest.mark.parametrize(
    ("indoor", "outdoor"), [("5", "-3"), ("35", "-3"), ("21", "-50"), ("21", "17")]
)
def test_boundary_values_remain_usable(ctl, indoor, outdoor):
    sensor, states, _ = ctl
    states["sensor.indoor"].state = indoor
    states["sensor.outdoor"].state = outdoor
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_PI


def test_summer_passthrough_is_capped(ctl):
    sensor, states, _ = ctl
    states["sensor.outdoor"].state = "30"
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_SUMMER
    assert sensor.state == MAX_FAKE_TEMP
    assert _pushed(sensor) == [MAX_FAKE_TEMP]
    # The real reading is still reported for diagnostics.
    assert sensor.extra_state_attributes["outdoor_temperature"] == 30.0


@pytest.mark.parametrize(("outdoor", "expected"), [("30", 25.0), ("-30", -30.0)])
def test_safe_mode_passthrough_caps_only_the_upper_limit(ctl, outdoor, expected):
    sensor, states, _ = ctl
    states["sensor.outdoor"].state = outdoor
    states["sensor.indoor"].state = "unavailable"
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_SAFE
    assert sensor.state == expected
    assert _pushed(sensor) == [expected]


# ── B3: fresh valid readings are not interruptions ───────────────────────────


@pytest.mark.parametrize("stage", ["prices", "forecast"])
def test_fresh_valid_reading_during_calculation_keeps_control(ctl, monkeypatch, stage):
    sensor, states, clock = ctl
    states["sensor.indoor"].state = "20.0"
    for _ in range(3):
        asyncio.run(sensor.async_update())
        clock[0] += timedelta(minutes=1)
    integral = sensor._pi._integral
    assert integral > 0.0
    calls = len(sensor.hass.services.calls)
    clock[0] += timedelta(minutes=10)  # output due

    original_prices = sensor._get_prices
    original_forecast = sensor._forecast_temps

    async def prices(cfg, now):
        if stage == "prices":
            states["sensor.outdoor"].state = "-3.4"
        return await original_prices(cfg, now)

    async def forecast():
        if stage == "forecast":
            states["sensor.indoor"].state = "20.1"
        return await original_forecast()

    monkeypatch.setattr(sensor, "_get_prices", prices)
    monkeypatch.setattr(sensor, "_forecast_temps", forecast)
    asyncio.run(sensor.async_update())

    attrs = sensor.extra_state_attributes
    assert attrs["mode"] == MODE_PI
    assert "temperature_input_status" not in attrs
    assert sensor.state is not None
    assert sensor._pi._integral > integral  # history kept and advanced
    assert len(sensor.hass.services.calls) > calls  # output still dispatched


def _subscribe_listeners(monkeypatch):
    listeners = []

    def subscribe(hass, entities, listener):
        listeners.append(listener)
        return lambda: listeners.remove(listener)

    monkeypatch.setattr(relay_guard, "async_track_state_change_event", subscribe)
    return listeners


def _emit(listeners, entity_id, state):
    event = SimpleNamespace(
        data={
            "entity_id": entity_id,
            "new_state": SimpleNamespace(state=state, attributes={}),
        }
    )
    for callback in list(listeners):
        callback(event)


def test_fresh_reading_during_active_renewal_keeps_pi_and_active(guarded, monkeypatch):
    sensor, states, clock, manager, receiver = guarded
    states["sensor.indoor"].state = "20.0"
    states["switch.relay"].state = "on"
    listeners = _subscribe_listeners(monkeypatch)
    base_sleep = relay_guard.asyncio.sleep
    armed = {"on": False}

    async def sleep(seconds):
        if armed["on"] and seconds == 3:
            states["sensor.outdoor"].state = "-3.4"
            _emit(listeners, "sensor.outdoor", "-3.4")
        await base_sleep(seconds)

    monkeypatch.setattr(relay_guard.asyncio, "sleep", sleep)

    async def scenario():
        for _ in range(5):
            await update(sensor, manager)
            clock[0] += timedelta(minutes=1)
        integral = sensor._pi._integral
        assert integral > 0.0
        armed["on"] = True
        await update(sensor, manager)  # output due -> ACTIVE renewal -> report
        return integral

    integral = asyncio.run(scenario())
    assert sensor._pi._integral >= integral
    assert sensor.state is not None
    assert "temperature_input_status" not in sensor.extra_state_attributes
    assert receiver.active
    assert manager.status == "healthy"
    assert listeners == []


@pytest.mark.parametrize("transient", ["unavailable", "85", "nan"])
def test_invalid_transient_during_active_renewal_still_revokes_grant(
    guarded, monkeypatch, transient
):
    sensor, states, clock, manager, receiver = guarded
    listeners = _subscribe_listeners(monkeypatch)
    base_sleep = relay_guard.asyncio.sleep

    async def sleep(seconds):
        if seconds == 2:  # relay off -> stabilization before the first ACTIVE
            _emit(listeners, "sensor.outdoor", transient)
        await base_sleep(seconds)

    monkeypatch.setattr(relay_guard.asyncio, "sleep", sleep)
    asyncio.run(update(sensor, manager))
    assert not receiver.active
    assert all(call[0] == "number" for call in receiver.calls)
