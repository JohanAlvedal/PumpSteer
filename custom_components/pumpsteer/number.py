"""Single user-facing economy preference for PumpSteer V3."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import CONF_SAVING_LEVEL, DOMAIN, PumpSteerEntryData
from .v3.pricing import (
    DEFAULT_SAVING_LEVEL,
    MAX_SAVING_LEVEL,
    MIN_SAVING_LEVEL,
    normalize_saving_level,
    price_policy_for_saving_level,
)

SAVING_LEVEL_DESCRIPTION = NumberEntityDescription(
    key=CONF_SAVING_LEVEL,
    translation_key=CONF_SAVING_LEVEL,
    icon="mdi:piggy-bank-outline",
    native_min_value=MIN_SAVING_LEVEL,
    native_max_value=MAX_SAVING_LEVEL,
    native_step=1,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the only V3 economy control."""
    del hass
    data: PumpSteerEntryData = entry.runtime_data
    async_add_entities([PumpSteerSavingLevel(entry, data)])


class PumpSteerSavingLevel(RestoreNumber, NumberEntity):
    """Select economic intent without granting the price planner authority."""

    _attr_has_entity_name = True
    entity_description = SAVING_LEVEL_DESCRIPTION

    def __init__(self, entry: ConfigEntry, data: PumpSteerEntryData) -> None:
        self._runtime = data.runtime
        self._attr_unique_id = f"{entry.entry_id}_{CONF_SAVING_LEVEL}"
        self._attr_native_value = DEFAULT_SAVING_LEVEL
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="PumpSteer",
            model="V3 Virtual Outdoor Temperature Controller",
        )

    async def async_added_to_hass(self) -> None:
        """Restore the preference and apply it to this runtime only."""
        await super().async_added_to_hass()
        restored = await self.async_get_last_number_data()
        value: object = DEFAULT_SAVING_LEVEL
        if restored is not None and restored.native_value is not None:
            value = restored.native_value
        try:
            level = normalize_saving_level(value)
        except (TypeError, ValueError):
            level = DEFAULT_SAVING_LEVEL
        self._set_level(level)

    async def async_set_native_value(self, value: float) -> None:
        """Apply one validated integer level without price-control authority."""
        self._set_level(normalize_saving_level(value))
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Show the derived policy and its deliberately absent authority."""
        policy = price_policy_for_saving_level(self.native_value)
        return {
            "mode": "shadow_only",
            "price_classification_requested": policy.classification_enabled,
            "cheap_percentile": policy.cheap_percentile,
            "expensive_percentile": policy.expensive_percentile,
            "price_planner_authority": False,
            "physical_control_authority": False,
        }

    def _set_level(self, level: int) -> None:
        self._attr_native_value = level
        self._runtime.set_saving_level(level)
