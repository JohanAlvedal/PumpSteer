"""Version-aware sensor platform dispatcher for PumpSteer."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform for the active PumpSteer generation."""
    if getattr(config_entry, "version", 1) >= 3:
        from .v3.ha.virtual_sensor import async_setup_virtual_sensor

        await async_setup_virtual_sensor(hass, config_entry, async_add_entities)
        return

    from .sensor_v2 import async_setup_entry as async_setup_v2_sensors

    await async_setup_v2_sensors(hass, config_entry, async_add_entities)


def __getattr__(name: str):
    """Keep legacy class imports working without loading V2 during V3 setup."""
    if name in {"PumpSteerSensor", "ThermalOutlookSensor"}:
        from . import sensor_v2

        return getattr(sensor_v2, name)
    raise AttributeError(name)
