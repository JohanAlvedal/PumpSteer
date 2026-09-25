from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from .relay_guard import OhmigoRelayGuard

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = [
        PumpSteerHolidaySwitch(entry),
        PumpSteerNotificationsSwitch(entry),
        PumpSteerOhmigoSwitch(entry),
        PumpSteerPreheatSwitch(entry),
    ]

    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    relay_guard = runtime.get("relay_guard") if isinstance(runtime, dict) else None
    if relay_guard is not None:
        entities.append(PumpSteerOhmigoRelayGuardSwitch(entry, relay_guard))

    async_add_entities(entities)


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
        self._attr_is_on = True
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


class PumpSteerPreheatSwitch(RestoreEntity, SwitchEntity):
    """Switch to enable or disable PumpSteer preheat boost."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_preheat_enabled"
        self._attr_name = "Preheat Boost"
        self._attr_icon = "mdi:radiator"
        self._attr_is_on = True
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


class PumpSteerOhmigoSwitch(RestoreEntity, SwitchEntity):
    """Switch to enable or disable automatic Ohmigo setpoint push."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_ohmigo_enabled"
        self._attr_name = "Ohmigo Push"
        self._attr_icon = "mdi:thermometer-lines"
        self._attr_is_on = True
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


class PumpSteerOhmigoRelayGuardSwitch(RestoreEntity, SwitchEntity):
    """Arm or disarm recovery of the optional Ohmigo Active/Bypass relay."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        relay_guard: OhmigoRelayGuard,
    ) -> None:
        self._entry = entry
        self._relay_guard = relay_guard
        self._remove_guard_listener = None

        self._attr_unique_id = f"{entry.entry_id}_ohmigo_relay_guard"
        self._attr_name = "Ohmigo Relay Guard"
        self._attr_icon = "mdi:shield-check"
        self._attr_is_on = False
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="Johan Alvedal",
            model="PumpSteer",
        )

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    @property
    def extra_state_attributes(self) -> dict:
        return self._relay_guard.diagnostics

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

        self._remove_guard_listener = self._relay_guard.async_add_listener(
            self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_guard_listener is not None:
            self._remove_guard_listener()
            self._remove_guard_listener = None
        await super().async_will_remove_from_hass()

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()
        self._relay_guard.async_guard_state_changed()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
        self._relay_guard.async_guard_state_changed()
