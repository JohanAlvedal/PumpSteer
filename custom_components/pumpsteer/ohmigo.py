"""PumpSteer — Ohmigo setpoint push logic."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .settings import OHMIGO_DEFAULT_INTERVAL_MINUTES, OHMIGO_HYSTERESIS_C

_LOGGER = logging.getLogger(__name__)


def _switch_entity_id(hass: HomeAssistant, entry_id: str) -> Optional[str]:
    registry = er.async_get(hass)
    return registry.async_get_entity_id("switch", DOMAIN, f"{entry_id}_ohmigo_enabled")


def _ohmigo_push_enabled(hass: HomeAssistant, entry_id: str) -> bool:
    switch_id = _switch_entity_id(hass, entry_id)
    if not switch_id:
        return True
    state = hass.states.get(switch_id)
    if state is None:
        return True
    return state.state == "on"


async def async_push_ohmigo(
    hass: HomeAssistant,
    entry: ConfigEntry,
    fake_temp: float,
    last_push_time: Optional[datetime],
) -> Optional[datetime]:
    cfg = {**entry.data, **entry.options}
    ohmigo_entity: str = cfg.get("ohmigo_entity", "")
    if not ohmigo_entity:
        return last_push_time

    if not _ohmigo_push_enabled(hass, entry.entry_id):
        return last_push_time

    interval_minutes: float = float(
        cfg.get("ohmigo_interval_minutes", OHMIGO_DEFAULT_INTERVAL_MINUTES)
    )
    now = dt_util.now()
    if last_push_time is not None:
        elapsed = (now - last_push_time).total_seconds() / 60.0
        if elapsed < interval_minutes:
            return last_push_time

    new_val = round(fake_temp * 2) / 2

    cur_state = hass.states.get(ohmigo_entity)
    if cur_state is not None:
        try:
            cur_val = float(cur_state.state)
            if abs(new_val - cur_val) < OHMIGO_HYSTERESIS_C:
                _LOGGER.debug(
                    "Ohmigo push skipped — within hysteresis (%.1f → %.1f)",
                    cur_val,
                    new_val,
                )
                return last_push_time
        except ValueError, TypeError:
            pass

    try:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": ohmigo_entity, "value": new_val},
            blocking=False,
        )
        _LOGGER.debug("Ohmigo push: %s → %.1f °C", ohmigo_entity, new_val)

        try:
            from homeassistant.components import logbook

            logbook.async_log_entry(
                hass,
                name="PumpSteer",
                message=f"Ohmigo push → {new_val} °C",
                domain=DOMAIN,
                entity_id=ohmigo_entity,
            )
        except Exception:
            pass

        return now
    except Exception as err:
        _LOGGER.warning("Ohmigo push failed for %s: %s", ohmigo_entity, err)
        return last_push_time
