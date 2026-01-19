"""PumpSteer integration"""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.integration import async_get_integration

from .const import DATA_VERSION, DOMAIN
from .ml_settings import validate_ml_settings
from .options_flow import PumpSteerOptionsFlowHandler
from .settings import validate_core_settings

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the PumpSteer integration"""
    try:
        validate_core_settings()
        validate_ml_settings()
    except ValueError as err:
        _LOGGER.error(
            "PumpSteer settings validation failed; setup aborted: %s",
            err,
        )
        return False

    integration = await async_get_integration(hass, DOMAIN)
    hass.data.setdefault(DOMAIN, {})[DATA_VERSION] = integration.version

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the PumpSteer integration"""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])


async def async_get_options_flow():
    """Return the options flow handler"""
    return PumpSteerOptionsFlowHandler()
