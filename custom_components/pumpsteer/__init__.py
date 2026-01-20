"""PumpSteer integration"""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DATA_VERSION, DOMAIN
from .ml_settings import validate_ml_settings
from .options_flow import PumpSteerOptionsFlowHandler
from .settings import validate_core_settings

_LOGGER = logging.getLogger(__name__)


async def _async_handle_options_update(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options updates by reloading the config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


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
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[DATA_VERSION] = integration.version
    domain_data.setdefault("unsub_options_listeners", {})[
        entry.entry_id
    ] = entry.add_update_listener(_async_handle_options_update)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the PumpSteer integration"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    domain_data = hass.data.get(DOMAIN, {})
    unsub_listeners = domain_data.get("unsub_options_listeners", {})
    unsubscribe = unsub_listeners.pop(entry.entry_id, None)
    if unsubscribe:
        unsubscribe()
    return unload_ok


async def async_get_options_flow():
    """Return the options flow handler"""
    return PumpSteerOptionsFlowHandler()
