"""PumpSteer heat pump controller."""

import importlib
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


async def _async_sync_panel(
    hass: HomeAssistant, exclude_entry_id: str | None = None
) -> None:
    """Add/remove the optional sidebar panel. Failures never block setup."""
    try:
        panel = await hass.async_add_import_executor_job(
            importlib.import_module, f"{__name__}.panel"
        )
        await panel.async_sync_panel(hass, exclude_entry_id)
    except Exception as err:
        _LOGGER.warning("PumpSteer panel could not be updated: %s", err)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload only when the optional relay entity itself changes."""
    await _async_sync_panel(hass)

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

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        runtime["options_unsub"] = entry.add_update_listener(_async_options_updated)
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

    await _async_sync_panel(hass)
    _LOGGER.info("PumpSteer integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload PumpSteer."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    await _async_sync_panel(hass, exclude_entry_id=entry.entry_id)

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
