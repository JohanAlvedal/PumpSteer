"""Diagnostics support for PumpSteer."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.redact import redact_data

from .const import DOMAIN

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a PumpSteer config entry."""
    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    domain_data = hass.data.get(DOMAIN, {})
    diagnostics_store = domain_data.get("diagnostics", {})
    debug_arrays = diagnostics_store.get(config_entry.entry_id, {})

    return {
        "config_entry": redact_data(config_entry.as_dict(), TO_REDACT),
        "entities": [entity.entity_id for entity in entities],
        "internal_state": debug_arrays,
    }
