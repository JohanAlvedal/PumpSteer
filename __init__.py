"""PumpSteer integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .options_flow import PumpSteerOptionsFlowHandler

DOMAIN = "virtualoutdoortemp"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])

async def async_get_options_flow(config_entry):
    return PumpSteerOptionsFlowHandler(config_entry)
