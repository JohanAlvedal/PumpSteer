"""Focused tests for the PumpSteer V3 climate presentation."""

from __future__ import annotations

import asyncio
import sys
import types
from enum import IntFlag, StrEnum
from types import SimpleNamespace

import pytest


climate_module = types.ModuleType("homeassistant.components.climate")
climate_const = types.ModuleType("homeassistant.components.climate.const")
coordinator_module = types.ModuleType("homeassistant.helpers.update_coordinator")


class ClimateEntity:
    pass


class CoordinatorEntity:
    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator


class HVACMode(StrEnum):
    AUTO = "auto"


class HVACAction(StrEnum):
    HEATING = "heating"
    IDLE = "idle"


class ClimateEntityFeature(IntFlag):
    TARGET_TEMPERATURE = 1


climate_module.ClimateEntity = ClimateEntity
climate_const.HVACMode = HVACMode
climate_const.HVACAction = HVACAction
climate_const.ClimateEntityFeature = ClimateEntityFeature
coordinator_module.CoordinatorEntity = CoordinatorEntity
sys.modules["homeassistant.components.climate"] = climate_module
sys.modules["homeassistant.components.climate.const"] = climate_const
sys.modules["homeassistant.helpers.update_coordinator"] = coordinator_module

from homeassistant import const as ha_const  # noqa: E402

ha_const.UnitOfTemperature = SimpleNamespace(CELSIUS="°C")

from custom_components.pumpsteer.climate import PumpSteerClimate  # noqa: E402
from custom_components.pumpsteer.const import PumpSteerEntryData  # noqa: E402


class Coordinator:
    def __init__(self) -> None:
        self.refreshes = 0

    async def async_request_refresh(self) -> None:
        self.refreshes += 1


class Runtime:
    def __init__(self) -> None:
        self.config = SimpleNamespace(target_temperature=21.0)
        observation = SimpleNamespace(indoor=SimpleNamespace(value=20.5))
        requested = SimpleNamespace(heating_request=1.0)
        self.latest = SimpleNamespace(observation=observation, requested=requested)

    def set_target_temperature(self, value: float) -> None:
        self.config.target_temperature = value


class LearningRuntime:
    def __init__(self) -> None:
        self.target_epochs: list[tuple[object, float]] = []

    async def async_note_target_change(
        self, *, changed_at, target_temperature: float
    ) -> None:
        self.target_epochs.append((changed_at, target_temperature))


class Entries:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def async_update_entry(self, entry, **kwargs) -> None:
        self.updates.append(kwargs)
        entry.data = kwargs["data"]


def test_climate_exposes_target_and_auto_only() -> None:
    coordinator = Coordinator()
    runtime = Runtime()
    entries = Entries()
    hass = SimpleNamespace(config_entries=entries)
    entry = SimpleNamespace(entry_id="entry", data={"target_temperature": 21.0})
    learning = LearningRuntime()
    entity = PumpSteerClimate(
        hass,
        entry,
        PumpSteerEntryData(
            runtime=runtime,
            coordinator=coordinator,
            learning_runtime=learning,
        ),
    )

    assert entity.hvac_modes == [HVACMode.AUTO]
    assert entity.hvac_mode is HVACMode.AUTO
    assert entity.current_temperature == 20.5
    assert entity.target_temperature == 21.0
    assert entity.hvac_action is HVACAction.IDLE

    asyncio.run(entity.async_set_temperature(temperature=22.5))

    assert entity.target_temperature == 22.5
    assert coordinator.refreshes == 1
    assert entry.data["target_temperature"] == 22.5
    assert len(entries.updates) == 1
    assert len(learning.target_epochs) == 1
    changed_at, changed_target = learning.target_epochs[0]
    assert changed_at.utcoffset().total_seconds() == 0
    assert changed_target == 22.5

    asyncio.run(entity.async_set_temperature(temperature=22.5))

    assert len(learning.target_epochs) == 1


def test_climate_rejects_non_auto_mode() -> None:
    hass = SimpleNamespace(config_entries=Entries())
    entity = PumpSteerClimate(
        hass,
        SimpleNamespace(entry_id="entry", data={"target_temperature": 21.0}),
        PumpSteerEntryData(runtime=Runtime(), coordinator=Coordinator()),
    )

    with pytest.raises(ValueError, match="only supports AUTO"):
        asyncio.run(entity.async_set_hvac_mode("off"))


def test_learning_epoch_failure_never_blocks_target_change() -> None:
    class FailingLearningRuntime:
        def __init__(self) -> None:
            self.stops = 0

        async def async_note_target_change(self, **kwargs) -> None:
            del kwargs
            raise RuntimeError("simulated learning failure")

        def stop(self) -> None:
            self.stops += 1

    coordinator = Coordinator()
    runtime = Runtime()
    learning = FailingLearningRuntime()
    entries = Entries()
    hass = SimpleNamespace(config_entries=entries)
    entry = SimpleNamespace(entry_id="entry", data={"target_temperature": 21.0})
    entity = PumpSteerClimate(
        hass,
        entry,
        PumpSteerEntryData(
            runtime=runtime,
            coordinator=coordinator,
            learning_runtime=learning,
        ),
    )

    asyncio.run(entity.async_set_temperature(temperature=22.0))

    assert runtime.config.target_temperature == 22.0
    assert entry.data["target_temperature"] == 22.0
    assert coordinator.refreshes == 1
    assert learning.stops == 1
