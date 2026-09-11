"""Independent scenarios for the PumpSteer V3 Home Assistant entrypoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import sys
from types import ModuleType, SimpleNamespace

from custom_components.pumpsteer import (
    async_setup_entry,
    async_unload_entry,
)
from custom_components.pumpsteer.config_flow import PumpSteerConfigFlow
from custom_components.pumpsteer.const import (
    CONF_INDOOR_ENTITY,
    CONF_OHMON_MQTT_BASE_TOPIC,
    CONF_OHMON_WATCHDOG_CONFIRMED,
    CONF_OUTDOOR_ENTITY,
    CONF_OUTPUT_MODE,
    CONF_TARGET_TEMPERATURE,
    OUTPUT_MODE_OHMON_MQTT,
    PLATFORMS,
)


START = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
INDOOR = "sensor.indoor"
OUTDOOR = "sensor.outdoor"


class FakeState:
    def __init__(self, value: str, source: str) -> None:
        self.state = value
        self.last_updated = START
        self.attributes = {"unit_of_measurement": "°C", "source": source}


class FakeStates:
    def __init__(self) -> None:
        self.values = {
            INDOOR: FakeState("19.0", INDOOR),
            OUTDOOR: FakeState("-5.0", OUTDOOR),
        }

    def get(self, entity_id: str):
        return self.values.get(entity_id)


class FakeConfigEntries:
    def __init__(self) -> None:
        self.forwarded: list[tuple[object, tuple[str, ...]]] = []
        self.unloaded: list[tuple[object, tuple[str, ...]]] = []
        self.updated: list[tuple[object, dict]] = []

    async def async_forward_entry_setups(self, entry, platforms) -> None:
        self.forwarded.append((entry, tuple(platforms)))

    async def async_unload_platforms(self, entry, platforms) -> bool:
        self.unloaded.append((entry, tuple(platforms)))
        return True

    def async_update_entry(self, entry, **changes) -> None:
        self.updated.append((entry, changes))
        if "data" in changes:
            entry.data = changes["data"]


class FakeHass:
    def __init__(self) -> None:
        self.states = FakeStates()
        self.config_entries = FakeConfigEntries()
        self.services = SimpleNamespace(
            has_service=lambda domain, service: (
                (domain, service) == ("mqtt", "publish")
            ),
            async_call=self._async_call,
        )
        self.service_calls: list[tuple[str, str, dict, bool]] = []

    async def _async_call(
        self, domain: str, service: str, data: dict, *, blocking: bool
    ) -> None:
        self.service_calls.append((domain, service, data, blocking))


class FakeEntry:
    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        self.data = {
            CONF_INDOOR_ENTITY: INDOOR,
            CONF_OUTDOOR_ENTITY: OUTDOOR,
            CONF_TARGET_TEMPERATURE: 21.0,
        }
        self.runtime_data = None
        self.unload_callbacks: list = []
        self.update_listener = None

    def async_on_unload(self, callback) -> None:
        self.unload_callbacks.append(callback)

    def add_update_listener(self, listener):
        self.update_listener = listener
        return lambda: None


def _coordinator_module() -> ModuleType:
    module = ModuleType("custom_components.pumpsteer.v3.ha.coordinator")

    class HomeAssistantStateProvider:
        def __init__(self, hass) -> None:
            self.hass = hass

        def get_state(self, entity_id):
            from custom_components.pumpsteer.v3.ha.runtime import RawState

            state = self.hass.states.get(entity_id)
            if state is None:
                return None
            return RawState(
                state.state,
                state.last_updated,
                state.attributes["unit_of_measurement"],
                entity_id,
            )

    class PumpSteerDataUpdateCoordinator:
        def __init__(self, hass, runtime) -> None:
            self.hass = hass
            self.runtime = runtime
            self.first_refreshes = 0
            self.cleanup_calls = 0

        async def async_config_entry_first_refresh(self) -> None:
            self.first_refreshes += 1
            await self.runtime.async_update(START)

        def async_start_source_tracking(self):
            def cleanup() -> None:
                self.cleanup_calls += 1

            return cleanup

    module.HomeAssistantStateProvider = HomeAssistantStateProvider
    module.PumpSteerDataUpdateCoordinator = PumpSteerDataUpdateCoordinator
    return module


def test_setup_owns_runtime_per_entry_and_loads_v3_platforms(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "custom_components.pumpsteer.v3.ha.coordinator",
        _coordinator_module(),
    )
    hass = FakeHass()
    first = FakeEntry("first")
    second = FakeEntry("second")

    assert asyncio.run(async_setup_entry(hass, first)) is True
    assert asyncio.run(async_setup_entry(hass, second)) is True

    assert PLATFORMS == ("climate", "number", "sensor")
    assert hass.config_entries.forwarded == [
        (first, ("climate", "number", "sensor")),
        (second, ("climate", "number", "sensor")),
    ]
    assert first.runtime_data is not second.runtime_data
    assert first.runtime_data.runtime is not second.runtime_data.runtime
    assert (
        first.runtime_data.learning_runtime is not second.runtime_data.learning_runtime
    )
    assert first.runtime_data.coordinator.first_refreshes == 1
    assert first.runtime_data.runtime.latest is not None
    assert first.runtime_data.runtime.latest.supervised.apply_physical is False
    assert len(first.unload_callbacks) == 3
    assert first.update_listener is not None
    for cleanup in first.unload_callbacks:
        cleanup()
    assert first.runtime_data.coordinator.cleanup_calls == 1
    assert first.runtime_data.learning_runtime.snapshot.status.value == "stopped"


def test_active_ohmon_entry_starts_bypassed_then_publishes_temperature_and_on(
    monkeypatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "custom_components.pumpsteer.v3.ha.coordinator",
        _coordinator_module(),
    )
    hass = FakeHass()
    hass.states.values[INDOOR].state = 19.0
    hass.states.values[OUTDOOR].state = -5.0
    entry = FakeEntry("active")
    entry.options = {
        CONF_OUTPUT_MODE: OUTPUT_MODE_OHMON_MQTT,
        CONF_OHMON_MQTT_BASE_TOPIC: "ohmonwifiplus/123456/",
        CONF_OHMON_WATCHDOG_CONFIRMED: True,
    }

    assert asyncio.run(async_setup_entry(hass, entry)) is True

    assert entry.runtime_data.runtime.latest.error is None
    expected_temperature = entry.runtime_data.runtime.latest.supervised.value
    payloads = [call[2]["payload"] for call in hass.service_calls]
    topics = [call[2]["topic"] for call in hass.service_calls]
    assert payloads == ["OFF", f"{expected_temperature:.2f}", "ON"]
    assert topics == [
        "ohmonwifiplus/123456/relay/set",
        "ohmonwifiplus/123456/temperature/set",
        "ohmonwifiplus/123456/relay/set",
    ]
    assert entry.runtime_data.runtime.physical_control_enabled is True
    assert entry.runtime_data.runtime.latest.supervised.apply_physical is True


def test_unload_uses_same_v3_platforms() -> None:
    hass = FakeHass()
    entry = FakeEntry("entry")

    assert asyncio.run(async_unload_entry(hass, entry)) is True

    assert hass.config_entries.unloaded == [
        (entry, ("climate", "number", "sensor"))
    ]


def test_config_form_has_exactly_three_fields() -> None:
    flow = PumpSteerConfigFlow()

    def show_form(**kwargs):
        return kwargs

    flow.async_show_form = show_form
    result = asyncio.run(flow.async_step_user())
    schema = result["data_schema"]

    assert set(schema) == {
        CONF_INDOOR_ENTITY,
        CONF_OUTDOOR_ENTITY,
        CONF_TARGET_TEMPERATURE,
    }


def test_same_sensor_is_rejected_even_when_entity_exists() -> None:
    flow = PumpSteerConfigFlow()
    flow.hass = SimpleNamespace(states=FakeStates())

    errors = flow._validate_input(
        {
            CONF_INDOOR_ENTITY: INDOOR,
            CONF_OUTDOOR_ENTITY: INDOOR,
            CONF_TARGET_TEMPERATURE: 21.0,
        }
    )

    assert errors[CONF_OUTDOOR_ENTITY] == "same_sensor"


def test_registry_entity_is_accepted_while_state_unavailable(monkeypatch) -> None:
    from custom_components.pumpsteer import config_flow

    class Registry:
        def async_get(self, entity_id: str):
            if entity_id in {INDOOR, OUTDOOR}:
                return SimpleNamespace(entity_id=entity_id)
            return None

    flow = PumpSteerConfigFlow()
    flow.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))
    monkeypatch.setattr(config_flow.er, "async_get", lambda _hass: Registry())

    errors = flow._validate_input(
        {
            CONF_INDOOR_ENTITY: INDOOR,
            CONF_OUTDOOR_ENTITY: OUTDOOR,
            CONF_TARGET_TEMPERATURE: 21.0,
        }
    )

    assert errors == {}


def test_climate_is_auto_only_and_target_update_persists_once() -> None:
    from homeassistant.components.climate.const import HVACAction, HVACMode

    from custom_components.pumpsteer.climate import PumpSteerClimate
    from custom_components.pumpsteer.const import PumpSteerEntryData

    class Coordinator:
        def __init__(self) -> None:
            self.refreshes = 0

        async def async_request_refresh(self) -> None:
            self.refreshes += 1

    class Runtime:
        def __init__(self) -> None:
            self.config = SimpleNamespace(target_temperature=21.0)
            self.latest = None

        def set_target_temperature(self, target: float) -> None:
            self.config.target_temperature = target

    hass = FakeHass()
    entry = FakeEntry("climate-entry")
    coordinator = Coordinator()
    runtime = Runtime()
    climate = PumpSteerClimate(
        hass,
        entry,
        PumpSteerEntryData(runtime=runtime, coordinator=coordinator),
    )

    assert climate.hvac_modes == [HVACMode.AUTO]
    assert climate.hvac_mode is HVACMode.AUTO
    assert all(mode.value != "off" for mode in climate.hvac_modes)
    assert climate.hvac_action is HVACAction.IDLE

    asyncio.run(climate.async_set_temperature(temperature=22.5))
    asyncio.run(climate.async_set_temperature(temperature=22.5))

    assert runtime.config.target_temperature == 22.5
    assert coordinator.refreshes == 2
    assert len(hass.config_entries.updated) == 1
    changed_entry, changes = hass.config_entries.updated[0]
    assert changed_entry is entry
    assert changes["data"] == {
        CONF_INDOOR_ENTITY: INDOOR,
        CONF_OUTDOOR_ENTITY: OUTDOOR,
        CONF_TARGET_TEMPERATURE: 22.5,
    }
