"""Switch entities for PumpSteer."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            PumpSteerHolidaySwitch(entry),
            PumpSteerNotificationsSwitch(entry),
        ]
    )


class PumpSteerHolidaySwitch(RestoreEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_holiday_mode"
        self._attr_name = "Holiday Mode"
        self._attr_icon = "mdi:beach"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="Johan Alvedal",
            model="PumpSteer",
        )

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()


class PumpSteerNotificationsSwitch(RestoreEntity, SwitchEntity):
    """Switch to enable or disable PumpSteer price notifications."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_notifications_enabled"
        self._attr_name = "Notifications"
        self._attr_icon = "mdi:bell"
        self._attr_is_on = True  # ON by default
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="Johan Alvedal",
            model="PumpSteer",
        )

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
