"""Optional PumpSteer sidebar panel (display only).

Imported lazily from __init__.py so the core integration never depends on
the frontend. Nothing here can influence control decisions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SHOW_PANEL_OPTION
from .settings import PUMPSTEER_VERSION

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "pumpsteer"
STATIC_URL = "/pumpsteer_static"
WEBCOMPONENT = "pumpsteer-panel"
_DATA_KEY = "pumpsteer_frontend"

# Entity keys exposed to the panel: (domain, unique_id suffix or "" for entry_id).
_ENTITY_MAP: dict[str, tuple[str, str]] = {
    "control": ("sensor", ""),
    "savings": ("sensor", "_estimated_savings"),
    "outlook": ("sensor", "_thermal_outlook"),
    "indoor": ("sensor", "_indoor_temperature"),
    "outdoor": ("sensor", "_outdoor_temperature"),
    "target_temperature": ("number", "_target_temperature"),
    "aggressiveness": ("number", "_aggressiveness"),
    "house_inertia": ("number", "_house_inertia"),
    "summer_threshold": ("number", "_summer_threshold"),
    "preheat": ("switch", "_preheat_enabled"),
    "holiday": ("switch", "_holiday_mode"),
    "holiday_start": ("datetime", "_holiday_start"),
    "holiday_end": ("datetime", "_holiday_end"),
}


@websocket_api.websocket_command({vol.Required("type"): "pumpsteer/entities"})
@callback
def _ws_entities(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Return the real entity IDs per config entry (no guessing in JS)."""
    registry = er.async_get(hass)
    result = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        entities = {
            key: registry.async_get_entity_id(
                domain, DOMAIN, f"{entry.entry_id}{suffix}"
            )
            for key, (domain, suffix) in _ENTITY_MAP.items()
        }
        result.append(
            {"entry_id": entry.entry_id, "title": entry.title, "entities": entities}
        )
    connection.send_result(msg["id"], result)


def _panel_wanted(hass: HomeAssistant, exclude_entry_id: str | None) -> bool:
    return any(
        bool(entry.options.get(SHOW_PANEL_OPTION, False))
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != exclude_entry_id
    )


async def async_sync_panel(
    hass: HomeAssistant, exclude_entry_id: str | None = None
) -> None:
    """Register or remove the sidebar panel to match the options."""
    state = hass.data.setdefault(
        _DATA_KEY, {"static": False, "ws": False, "panel": False}
    )
    wanted = _panel_wanted(hass, exclude_entry_id)

    if wanted and not state["panel"]:
        if not state["static"]:
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        STATIC_URL, str(Path(__file__).parent / "frontend"), False
                    )
                ]
            )
            state["static"] = True
        if not state["ws"]:
            websocket_api.async_register_command(hass, _ws_entities)
            state["ws"] = True
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=WEBCOMPONENT,
            sidebar_title="PumpSteer",
            sidebar_icon="mdi:heat-pump-outline",
            # Version query busts the browser cache after updates.
            module_url=f"{STATIC_URL}/pumpsteer-panel.js?v={PUMPSTEER_VERSION}",
            require_admin=False,
        )
        state["panel"] = True
        _LOGGER.info("PumpSteer panel registered at /%s", PANEL_URL_PATH)
    elif not wanted and state["panel"]:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        state["panel"] = False
        _LOGGER.info("PumpSteer panel removed")
