"""Regression tests for V3 startup recovery when the first refresh fails."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

from custom_components.pumpsteer import async_setup_entry
from custom_components.pumpsteer.const import (
    CONF_INDOOR_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_TARGET_TEMPERATURE,
    PLATFORMS,
)

INDOOR = "sensor.indoor"
OUTDOOR = "sensor.outdoor"


class FakeConfigEntries:
    """Record platform forwarding without loading Home Assistant platforms."""

    def __init__(self) -> None:
        self.forwarded: list[tuple[object, tuple[str, ...]]] = []

    async def async_forward_entry_setups(self, entry, platforms) -> None:
        self.forwarded.append((entry, tuple(platforms)))


class FakeHass:
    """Provide the minimal Home Assistant boundary required by setup."""

    def __init__(self) -> None:
        self.config_entries = FakeConfigEntries()
        self.services = SimpleNamespace(
            has_service=lambda _domain, _service: False,
            async_call=self._async_call,
        )

    async def _async_call(self, *_args, **_kwargs) -> None:
        return None


class FakeEntry:
    """Provide one minimal PumpSteer config entry."""

    def __init__(self) -> None:
        self.entry_id = "startup-refresh-failure"
        self.data = {
            CONF_INDOOR_ENTITY: INDOOR,
            CONF_OUTDOOR_ENTITY: OUTDOOR,
            CONF_TARGET_TEMPERATURE: 21.0,
        }
        self.options = {}
        self.runtime_data = None
        self.unload_callbacks: list = []

    def async_on_unload(self, callback) -> None:
        self.unload_callbacks.append(callback)

    def add_update_listener(self, _listener):
        return lambda: None


def _failing_coordinator_module() -> ModuleType:
    """Return a coordinator module whose initial refresh always fails."""
    module = ModuleType("custom_components.pumpsteer.v3.ha.coordinator")

    class HomeAssistantStateProvider:
        def __init__(self, hass) -> None:
            self.hass = hass

        def get_state(self, _entity_id):
            return None

    class PumpSteerDataUpdateCoordinator:
        def __init__(self, hass, runtime) -> None:
            self.hass = hass
            self.runtime = runtime
            self.refreshes = 0
            self.cleanup_calls = 0

        async def async_refresh(self) -> None:
            self.refreshes += 1
            raise RuntimeError("simulated initial refresh failure")

        def async_start_source_tracking(self):
            def cleanup() -> None:
                self.cleanup_calls += 1

            return cleanup

    module.HomeAssistantStateProvider = HomeAssistantStateProvider
    module.PumpSteerDataUpdateCoordinator = PumpSteerDataUpdateCoordinator
    return module


def test_initial_refresh_failure_keeps_v3_platforms_loaded(monkeypatch) -> None:
    """A failed first refresh must not make PumpSteer entities disappear."""
    monkeypatch.setitem(
        sys.modules,
        "custom_components.pumpsteer.v3.ha.coordinator",
        _failing_coordinator_module(),
    )
    hass = FakeHass()
    entry = FakeEntry()

    assert asyncio.run(async_setup_entry(hass, entry)) is True

    assert hass.config_entries.forwarded == [(entry, tuple(PLATFORMS))]
    assert entry.runtime_data is not None
    assert entry.runtime_data.coordinator.refreshes == 1
    assert len(entry.unload_callbacks) >= 2
