"""Sensor platform for PumpSteer V3 with legacy import compatibility."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PumpSteer V3 sensor platform."""
    from .v3.ha.virtual_sensor import async_setup_virtual_sensor

    await async_setup_virtual_sensor(hass, config_entry, async_add_entities)


def __getattr__(name: str):
    """Keep legacy imports working without loading V2 during V3 setup."""
    if name in {"PumpSteerSensor", "ThermalOutlookSensor", "MODE_SAFE"}:
        from . import sensor_v2

        return getattr(sensor_v2, name)
    raise AttributeError(name)
