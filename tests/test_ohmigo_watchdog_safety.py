"""Actual controller/Guard code with stubbed HA and a simulated receiver."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_temperature_input_safety import control, setup_sensor  # noqa: F401

from custom_components.pumpsteer import ohmigo, relay_guard


class Receiver:
    """Two explicit hypotheses; number resets are NOT hardware facts."""

    def __init__(self, clock, number_renews=False):
        self.clock = clock
        self.number_renews = number_renews
        self.active_at = None
        self.value = None
        self.connected = True
        self.calls = []

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value
        if not value:
            self.active_at = None  # loss latches BYPASS until another ACTIVE

    @property
    def active(self):
        return (
            self.connected
            and self.active_at is not None
            and (self.clock[0] - self.active_at).total_seconds() < 900
        )

    async def dispatch(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))
        if not self.connected:
            raise RuntimeError("simulated communication failure")
        if domain == "number":
            self.value = data["value"]
            if self.number_renews and self.active:
                self.active_at = self.clock[0]
        elif domain == "switch":
            self.active_at = self.clock[0]


@pytest.fixture
def rig(control, monkeypatch):
    sensor, states, clock = control
    entry = sensor._config_entry
    entry.options.pop("modbus_service")
    entry.options["ohmigo_relay_entity"] = "switch.relay"
    states["switch.guard"] = SimpleNamespace(state="on", attributes={})
    states["switch.relay"] = SimpleNamespace(state="off", attributes={})
    registry = SimpleNamespace(
        async_get_entity_id=lambda domain, platform, uid: (
            "switch.guard"
            if uid.endswith("_ohmigo_relay_guard")
            else "switch.push"
            if uid.endswith("_ohmigo_enabled")
            else None
        )
    )
    monkeypatch.setattr(ohmigo.er, "async_get", lambda hass: registry)
    manager = relay_guard.OhmigoRelayGuard(sensor.hass, entry, "switch.relay")
    manager._started = True
    sensor.hass.data = {"pumpsteer": {entry.entry_id: {"relay_guard": manager}}}
    sensor.hass.async_create_task = asyncio.create_task
    receiver = Receiver(clock)

    async def dispatch(domain, service, data, blocking=False):
        await receiver.dispatch(domain, service, data, blocking)
        if domain == "switch" and receiver.connected:
            states["switch.relay"].state = "on"

    sensor.hass.services.async_call = dispatch
    original_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await original_sleep(0)

    monkeypatch.setattr(relay_guard.asyncio, "sleep", fast_sleep)
    return sensor, states, clock, manager, receiver


async def update(sensor, manager):
    await sensor.async_update()
    if manager._recovery_task is not None:
        await manager._recovery_task


def test_guard_does_not_activate_without_validated_temperature_write(rig):
    sensor, states, clock, manager, receiver = rig
    states["sensor.outdoor"].state = "unavailable"

    async def scenario():
        await update(sensor, manager)
        await manager.async_check("watchdog_bypass")

    asyncio.run(scenario())
    assert receiver.calls == []


@pytest.mark.parametrize("number_renews", [False, True])
def test_normal_push_keeps_active_with_distinct_watchdog(rig, number_renews):
    sensor, states, clock, manager, receiver = rig
    receiver.number_renews = number_renews

    async def scenario():
        for minute in range(31):
            if minute:
                clock[0] += timedelta(minutes=1)
            await update(sensor, manager)
            assert receiver.active, (minute, receiver.calls)
        active = [call for call in receiver.calls if call[0] == "switch"]
        number = [call for call in receiver.calls if call[0] == "number"]
        assert len(active) == len(number) == 7
        assert all(call[3] for call in number)

    asyncio.run(scenario())


@pytest.mark.parametrize("number_renews", [False, True])
def test_invalid_sources_cannot_recover_old_command_after_watchdog(rig, number_renews):
    sensor, states, clock, manager, receiver = rig
    receiver.number_renews = number_renews

    async def scenario():
        await update(sensor, manager)
        assert receiver.active
        before = len(receiver.calls)
        states["sensor.outdoor"].state = "unavailable"
        for _ in range(4):
            clock[0] += timedelta(seconds=300)
            states["switch.relay"].state = "on" if receiver.active else "off"
            await update(sensor, manager)
            await manager.async_check("periodic")
        assert not receiver.active
        assert len(receiver.calls) == before
        states["sensor.outdoor"].state = "-4"
        await manager.async_check("source_recovered_before_output")
        assert not receiver.active
        await update(sensor, manager)
        assert receiver.active
        assert receiver.calls[-2][0] == "number"
        assert receiver.calls[-1][0] == "switch"

    asyncio.run(scenario())


def test_restored_startup_and_recovery_before_next_write(rig):
    sensor, states, clock, manager, receiver = rig

    async def scenario():
        for key in ("sensor.indoor", "sensor.outdoor"):
            states[key].attributes = {"restored": True}
        await update(sensor, manager)
        await manager.async_check("startup")
        assert receiver.calls == []
        for key in ("sensor.indoor", "sensor.outdoor"):
            states[key].attributes = {}
        await update(sensor, manager)
        assert receiver.active
        before = len(receiver.calls)
        states["sensor.outdoor"].state = "unavailable"
        await update(sensor, manager)
        states["switch.relay"].state = "off"
        states["sensor.outdoor"].state = "-4"
        clock[0] += timedelta(seconds=1)
        await update(sensor, manager)
        await manager.async_check("recovered_before_output_interval")
        assert len(receiver.calls) == before

    asyncio.run(scenario())


def test_number_failure_does_not_authorize_active(rig):
    sensor, states, clock, manager, receiver = rig
    receiver.connected = False

    async def scenario():
        await update(sensor, manager)
        receiver.connected = True
        await manager.async_check("mqtt_reconnected")
        assert not receiver.active
        assert all(call[0] == "number" for call in receiver.calls)
        await update(sensor, manager)
        assert receiver.active

    asyncio.run(scenario())


def test_safe_mode_authentic_outdoor_keeps_active(rig):
    sensor, states, clock, manager, receiver = rig
    states.pop("sensor.indoor")

    async def scenario():
        for _ in range(5):
            await update(sensor, manager)
            assert receiver.active
            assert receiver.value == -3.5
            clock[0] += timedelta(seconds=300)

    asyncio.run(scenario())


@pytest.mark.parametrize("gate", ["switch.guard", "switch.push", "switch.relay"])
def test_ineligible_grant_cannot_be_saved_for_later(rig, gate):
    sensor, states, clock, manager, receiver = rig

    async def scenario():
        states[gate].state = "unavailable" if gate == "switch.relay" else "off"
        await update(sensor, manager)
        before = len(receiver.calls)
        states[gate].state = "off" if gate == "switch.relay" else "on"
        await manager.async_check("gate_reenabled_without_write")
        assert len(receiver.calls) == before

    asyncio.run(scenario())


def test_new_grant_during_recovery_is_also_consumed(rig):
    sensor, states, clock, manager, receiver = rig
    original = sensor.hass.services.async_call

    async def dispatch(domain, service, data, blocking=False):
        await original(domain, service, data, blocking)
        if domain == "switch":
            manager._temperature_check = lambda: True

    sensor.hass.services.async_call = dispatch

    async def scenario():
        await update(sensor, manager)
        before = len(receiver.calls)
        await manager.async_check("periodic")
        assert len(receiver.calls) == before

    asyncio.run(scenario())


@pytest.mark.parametrize("minutes", [15, 20, 60, 0, float("nan")])
def test_unsafe_output_interval_cannot_authorize_active(rig, minutes):
    sensor, states, clock, manager, receiver = rig
    sensor._config_entry.options["ohmigo_interval_minutes"] = minutes

    async def scenario():
        await update(sensor, manager)
        assert not receiver.active
        assert all(call[0] != "switch" for call in receiver.calls)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["mqtt", "power"])
def test_communication_loss_bypasses_and_requires_new_delivered_write(rig, failure):
    sensor, states, clock, manager, receiver = rig

    async def scenario():
        await update(sensor, manager)
        assert receiver.active
        receiver.connected = False  # both losses mean no delivery and BYPASS
        assert not receiver.active
        states["switch.relay"].state = "off"
        clock[0] += timedelta(seconds=300)
        await update(sensor, manager)
        assert not receiver.active
        receiver.connected = True
        before = len(receiver.calls)
        await manager.async_check("reconnect")
        assert len(receiver.calls) == before
        assert not receiver.active
        await update(sensor, manager)
        assert receiver.active

    asyncio.run(scenario())


@pytest.mark.parametrize("reported_relay", ["on", "off", "unknown", "unavailable"])
def test_restored_relay_state_cannot_authorize_without_new_write(rig, reported_relay):
    sensor, states, clock, manager, receiver = rig
    states["switch.relay"].state = reported_relay
    states["switch.relay"].attributes = {"restored": True}
    asyncio.run(manager.async_check("restored_registry_state"))
    assert receiver.calls == []


def test_active_service_failures_are_bounded_and_not_independently_retried(rig):
    sensor, states, clock, manager, receiver = rig
    original = sensor.hass.services.async_call
    attempts = []

    async def dispatch(domain, service, data, blocking=False):
        if domain == "switch":
            attempts.append(data)
            raise RuntimeError("simulated ACTIVE delivery failure")
        await original(domain, service, data, blocking)

    sensor.hass.services.async_call = dispatch

    async def scenario():
        await update(sensor, manager)
        assert len(attempts) == 3
        assert not receiver.active
        await manager.async_check("periodic")
        await update(sensor, manager)
        assert len(attempts) == 3
        sensor.hass.services.async_call = original
        clock[0] += timedelta(seconds=300)
        await update(sensor, manager)
        assert receiver.active

    asyncio.run(scenario())


def test_source_flap_during_guard_stabilization_revokes_grant(rig, monkeypatch):
    sensor, states, clock, manager, receiver = rig
    listeners = []

    def subscribe(hass, entities, listener):
        listeners.append(listener)
        return lambda: listeners.remove(listener)

    monkeypatch.setattr(relay_guard, "async_track_state_change_event", subscribe)
    fast_sleep = relay_guard.asyncio.sleep

    async def flap(seconds):
        if seconds == 2:
            states["sensor.outdoor"].state = "unavailable"
            for callback in list(listeners):
                callback(SimpleNamespace(data={"entity_id": "sensor.outdoor"}))
            states["sensor.outdoor"].state = "-3.3"
        await fast_sleep(seconds)

    monkeypatch.setattr(relay_guard.asyncio, "sleep", flap)
    asyncio.run(update(sensor, manager))
    assert not receiver.active
    assert all(call[0] == "number" for call in receiver.calls)
    assert listeners == []


def test_sensor_stall_and_backward_ha_clock_cannot_extend_active(rig):
    sensor, states, clock, manager, receiver = rig
    receiver.clock = [clock[0]]  # independent, monotonic receiver timeline

    async def scenario():
        await update(sensor, manager)
        assert receiver.active
        clock[0] -= timedelta(days=1)
        receiver.clock[0] += timedelta(seconds=900)
        states["switch.relay"].state = "off"
        await update(sensor, manager)  # temperature interval is not yet due
        await manager.async_check("periodic")
        assert not receiver.active
        assert len(receiver.calls) == 2

    asyncio.run(scenario())


def test_flap_during_number_await_does_not_authorize_active(rig, monkeypatch):
    sensor, states, clock, manager, receiver = rig
    listeners = []
    original = sensor.hass.services.async_call

    def subscribe(hass, entities, listener):
        listeners.append(listener)
        return lambda: listeners.remove(listener)

    monkeypatch.setattr(relay_guard, "async_track_state_change_event", subscribe)

    async def dispatch(domain, service, data, blocking=False):
        await original(domain, service, data, blocking)
        if domain == "number":
            states["sensor.outdoor"].state = "unavailable"
            for callback in list(listeners):
                callback(SimpleNamespace(data={"entity_id": "sensor.outdoor"}))
            states["sensor.outdoor"].state = "-3.3"
            await asyncio.sleep(0)

    sensor.hass.services.async_call = dispatch
    asyncio.run(update(sensor, manager))
    assert all(call[0] == "number" for call in receiver.calls)
    assert not receiver.active
    assert listeners == []


def test_unload_while_number_handler_waits_cannot_activate(rig):
    sensor, states, clock, manager, receiver = rig
    original = sensor.hass.services.async_call

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def dispatch(domain, service, data, blocking=False):
            if domain == "number":
                entered.set()
                await release.wait()
            await original(domain, service, data, blocking)

        sensor.hass.services.async_call = dispatch
        task = asyncio.create_task(sensor.async_update())
        await entered.wait()
        sensor._temperature_unloaded = True
        await manager.async_stop()
        release.set()
        await task
        assert not receiver.active
        assert all(call[0] == "number" for call in receiver.calls)
        # A new instance (reload) also starts without old authorization.
        replacement = relay_guard.OhmigoRelayGuard(
            sensor.hass, sensor._config_entry, "switch.relay"
        )
        await replacement.async_check("reload")
        assert not receiver.active

    asyncio.run(scenario())
