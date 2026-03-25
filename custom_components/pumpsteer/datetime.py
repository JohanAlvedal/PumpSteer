"""Datetime entities for PumpSteer."""
from __future__ import annotations
import logging
from datetime import datetime
from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.dt as dt_util
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATETIME_ENTITIES = [
    ("holiday_start", "Holiday Start", "mdi:calendar-arrow-right"),
    ("holiday_end",   "Holiday End",   "mdi:calendar-arrow-left"),
]

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([
        PumpSteerDateTimeEntity(entry, key, name, icon)
        for key, name, icon in DATETIME_ENTITIES
    ])


class PumpSteerDateTimeEntity(RestoreEntity, DateTimeEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, key: str, name: str, icon: str) -> None:
        self._entry = entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value: datetime | None = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="Johan Alvedal",
            model="PumpSteer",
        )

    @property
    def native_value(self) -> datetime | None:
        return self._attr_native_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable", ""):
            parsed = dt_util.parse_datetime(last.state)
            if parsed is not None:
                self._attr_native_value = parsed

    async def async_set_value(self, value: datetime) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
