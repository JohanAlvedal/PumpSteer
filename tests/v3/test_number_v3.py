"""Tests for the V3 saving-level number entity."""

from __future__ import annotations

import asyncio
import sys
import types
from dataclasses import dataclass
from enum import StrEnum
from types import SimpleNamespace

number_module = types.ModuleType("homeassistant.components.number")


class NumberEntity:
    @property
    def native_value(self):
        return self._attr_native_value

    def async_write_ha_state(self) -> None:
        self.write_count = getattr(self, "write_count", 0) + 1


class RestoreNumber:
    restored = None

    async def async_added_to_hass(self) -> None:
        return None

    async def async_get_last_number_data(self):
        return self.restored


@dataclass
class NumberEntityDescription:
    key: str
    translation_key: str
    icon: str
    native_min_value: int
    native_max_value: int
    native_step: int
    mode: object


class NumberMode(StrEnum):
    SLIDER = "slider"


number_module.NumberEntity = NumberEntity
number_module.RestoreNumber = RestoreNumber
number_module.NumberEntityDescription = NumberEntityDescription
number_module.NumberMode = NumberMode
sys.modules["homeassistant.components.number"] = number_module

from custom_components.pumpsteer.const import PumpSteerEntryData
from custom_components.pumpsteer.number import (
    SAVING_LEVEL_DESCRIPTION,
    PumpSteerSavingLevel,
    async_setup_entry,
)


class Runtime:
    def __init__(self) -> None:
        self.config = SimpleNamespace(saving_level=3)
        self.levels: list[int] = []

    def set_saving_level(self, level: int) -> None:
        self.config.saving_level = level
        self.levels.append(level)


def data(runtime=None) -> PumpSteerEntryData:
    return PumpSteerEntryData(
        runtime=runtime or Runtime(),
        coordinator=SimpleNamespace(),
    )


def test_setup_adds_exactly_one_v3_number() -> None:
    added = []
    entry = SimpleNamespace(entry_id="entry", runtime_data=data())

    asyncio.run(async_setup_entry(None, entry, added.extend))

    assert len(added) == 1
    assert isinstance(added[0], PumpSteerSavingLevel)
    assert SAVING_LEVEL_DESCRIPTION.native_min_value == 0
    assert SAVING_LEVEL_DESCRIPTION.native_max_value == 5
    assert SAVING_LEVEL_DESCRIPTION.native_step == 1


def test_default_and_level_change_update_runtime_only() -> None:
    runtime = Runtime()
    entity = PumpSteerSavingLevel(
        SimpleNamespace(entry_id="entry"),
        data(runtime),
    )

    assert entity.native_value == 3
    assert entity.extra_state_attributes == {
        "mode": "shadow_only",
        "price_classification_requested": True,
        "cheap_percentile": 30,
        "expensive_percentile": 80,
        "price_planner_authority": False,
        "physical_control_authority": False,
    }

    asyncio.run(entity.async_set_native_value(4.0))

    assert entity.native_value == 4
    assert runtime.levels == [4]
    assert entity.extra_state_attributes["cheap_percentile"] == 35
    assert entity.extra_state_attributes["expensive_percentile"] == 70
    assert entity.write_count == 1


def test_restore_applies_valid_level_and_rejects_corrupt_state() -> None:
    runtime = Runtime()
    entity = PumpSteerSavingLevel(
        SimpleNamespace(entry_id="entry"),
        data(runtime),
    )
    entity.restored = SimpleNamespace(native_value=5.0)

    asyncio.run(entity.async_added_to_hass())

    assert entity.native_value == 5
    assert runtime.levels == [5]

    fallback_runtime = Runtime()
    fallback = PumpSteerSavingLevel(
        SimpleNamespace(entry_id="other"),
        data(fallback_runtime),
    )
    fallback.restored = SimpleNamespace(native_value=float("nan"))

    asyncio.run(fallback.async_added_to_hass())

    assert fallback.native_value == 3
    assert fallback_runtime.levels == [3]


def test_number_cannot_enable_price_or_physical_control() -> None:
    runtime = Runtime()
    entity = PumpSteerSavingLevel(
        SimpleNamespace(entry_id="entry"),
        data(runtime),
    )

    asyncio.run(entity.async_set_native_value(5))

    assert entity.extra_state_attributes["price_planner_authority"] is False
    assert entity.extra_state_attributes["physical_control_authority"] is False
    assert not hasattr(entity, "async_publish")
    assert not hasattr(entity, "apply_physical")
