"""PumpSteer integration"""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .options_flow import PumpSteerOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)
DOMAIN = "pumpsteer"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the PumpSteer integration"""
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the PumpSteer integration"""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])


async def async_get_options_flow():
    """Return the options flow handler"""
    return PumpSteerOptionsFlowHandler()
