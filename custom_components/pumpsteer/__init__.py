"""PumpSteer heat pump controller."""

import logging
from contextlib import suppress
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .notify import async_setup_notifications
from .relay_guard import configured_relay_entity, create_relay_guard

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "number", "switch", "datetime"]


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload only when the optional relay entity itself changes."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not isinstance(runtime, dict):
        return

    old_relay = runtime.get("relay_entity", "")
    new_relay = configured_relay_entity(entry)
    if old_relay != new_relay:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PumpSteer from a config entry."""
    runtime: dict[str, Any] = {}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    runtime["notification_unsub"] = async_setup_notifications(hass, entry)
    runtime["relay_entity"] = configured_relay_entity(entry)
    runtime["relay_guard"] = create_relay_guard(hass, entry)
    runtime["options_unsub"] = entry.add_update_listener(_async_options_updated)

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        relay_guard = runtime["relay_guard"]
        if relay_guard is not None:
            relay_guard.async_start()
    except Exception:
        for key in ("options_unsub", "notification_unsub"):
            callback = runtime.get(key)
            if callable(callback):
                with suppress(Exception):
                    callback()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        raise

    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload PumpSteer."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    runtime = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})
    if isinstance(runtime, dict):
        relay_guard = runtime.get("relay_guard")
        if relay_guard is not None:
            await relay_guard.async_stop()

        for key in ("options_unsub", "notification_unsub"):
            callback = runtime.get(key)
            if callable(callback):
                with suppress(Exception):
                    callback()

    return True
