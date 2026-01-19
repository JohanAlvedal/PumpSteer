"""Diagnostics support for PumpSteer."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


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
        "entities": [entity.entity_id for entity in entities],
        "debug_arrays": debug_arrays,
    }
