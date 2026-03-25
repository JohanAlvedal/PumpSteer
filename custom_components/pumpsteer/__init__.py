"""PumpSteer — Ngenic-inspired heat pump controller."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .notify import async_setup_notifications

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "number", "switch", "datetime"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PumpSteer from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = async_setup_notifications(hass, entry)
    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload PumpSteer."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, lambda: None)()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
