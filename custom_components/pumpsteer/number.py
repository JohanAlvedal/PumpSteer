"""Number entities for PumpSteer."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


NUMBER_ENTITIES: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key="target_temperature",
        name="Target Temperature",
        icon="mdi:thermometer",
        native_min_value=16.0,
        native_max_value=27.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.SLIDER,
    ),
    NumberEntityDescription(
        key="summer_threshold",
        name="Summer Mode Threshold",
        icon="mdi:weather-sunny",
        native_min_value=10.0,
        native_max_value=30.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.SLIDER,
    ),
    NumberEntityDescription(
        key="aggressiveness",
        name="Saving Level",
        icon="mdi:lightning-bolt-circle",
        native_min_value=0.0,
        native_max_value=5.0,
        native_step=1.0,
        mode=NumberMode.SLIDER,
    ),
    NumberEntityDescription(
        key="house_inertia",
        name="House Thermal Mass",
        icon="mdi:home-thermometer",
        native_min_value=0.5,
        native_max_value=10.0,
        native_step=0.5,
        mode=NumberMode.SLIDER,
    ),
)

DEFAULT_VALUES: dict[str, float] = {
    "target_temperature": 21.0,
    "summer_threshold": 17.0,
    "aggressiveness": 3.0,
    "house_inertia": 2.0,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PumpSteer number entities."""
    entities = [
        PumpSteerNumberEntity(entry, description)
        for description in NUMBER_ENTITIES
    ]
    _LOGGER.debug("Adding %s PumpSteer number entities", len(entities))
    async_add_entities(entities)


class PumpSteerNumberEntity(RestoreNumber, NumberEntity):
    """PumpSteer number entity."""

    _attr_has_entity_name = False

    def __init__(
        self,
        entry: ConfigEntry,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        self.entity_description = description
        self._entry = entry

        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = f"PumpSteer {description.name}"
        self._attr_native_value = DEFAULT_VALUES[description.key]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="Johan Alvedal",
            model="PumpSteer",
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._attr_native_value

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None and last_number_data.native_value is not None:
            self._attr_native_value = last_number_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return extra state attributes."""
        if self.entity_description.key == "aggressiveness":
            return {
                "description_0": "No price control, pure comfort",
                "description_1": "Very gentle, barely noticeable",
                "description_2": "Mild saving",
                "description_3": "Balanced (recommended)",
                "description_4": "Aggressive saving",
                "description_5": "Maximum saving, can get cold",
            }

        if self.entity_description.key == "house_inertia":
            return {
                "low_range": "0.5-2.0 lightweight house, reacts quickly",
                "mid_range": "2.0-4.0 typical house",
                "high_range": "4.0-10.0 heavy house, slow to heat/cool",
            }

        return {}
