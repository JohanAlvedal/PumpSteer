"""PumpSteer integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging

from .options_flow import PumpSteerOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)
DOMAIN = "pumpsteer"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the PumpSteer integration."""
    # Set up the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the PumpSteer integration."""
    # Unload the sensor platform
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])


async def async_get_options_flow(config_entry):
    """Return the options flow handler."""
    return PumpSteerOptionsFlowHandler(config_entry)
