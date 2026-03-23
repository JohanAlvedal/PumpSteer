"""PumpSteer — Ngenic-inspired heat pump controller."""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
DOMAIN = "pumpsteer"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PumpSteer from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload PumpSteer."""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
