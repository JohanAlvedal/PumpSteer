"""PumpSteer — Ohmigo setpoint push logic.

Pushes the fake outdoor temperature computed by PumpSteer to an Ohmigo
number entity (e.g. number.ohmonwifiplus_854608_temperature_set) so that
users do not need a separate HA automation for this.

Configuration (all in options_flow):
    ohmigo_entity        — target number entity (leave empty to disable)
    ohmigo_interval      — minimum minutes between pushes (default from settings)

The push is also gated by the "Ohmigo Push" switch entity so users can
disable it without touching the options flow.

Rounding: nearest 0.5 °C — identical to the reference YAML automation.
Hysteresis: skip push when |new - current| < 0.2 °C.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import homeassistant.util.dt as dt_util
from homeassistant.components import logbook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .settings import OHMIGO_DEFAULT_INTERVAL_MINUTES, OHMIGO_HYSTERESIS_C

_LOGGER = logging.getLogger(__name__)


def _switch_entity_id(hass: HomeAssistant, entry_id: str) -> Optional[str]:
    """Return entity_id for the PumpSteer Ohmigo Push switch."""
    registry = er.async_get(hass)
    return registry.async_get_entity_id("switch", DOMAIN, f"{entry_id}_ohmigo_enabled")


def _ohmigo_push_enabled(hass: HomeAssistant, entry_id: str) -> bool:
    """Return True if the Ohmigo Push switch is on (fail-open if unavailable)."""
    switch_id = _switch_entity_id(hass, entry_id)
    if not switch_id:
        return True  # switch not yet registered — allow push
    state = hass.states.get(switch_id)
    if state is None:
        return True  # fail-open
    return state.state == "on"


async def async_push_ohmigo(
    hass: HomeAssistant,
    entry: ConfigEntry,
    fake_temp: float,
    last_push_time: Optional[datetime],
) -> Optional[datetime]:
    """Push fake_temp to the configured Ohmigo number entity if appropriate.

    Returns the updated last_push_time (either the previous value or `now`
    if a push was performed), so the caller can track throttling state.

    Args:
        hass:            Home Assistant instance.
        entry:           Active config entry (data + options are merged inside).
        fake_temp:       The fake outdoor temperature to push (°C).
        last_push_time:  Timestamp of the previous successful push, or None.

    Returns:
        datetime of the push that was performed, or last_push_time unchanged
        if no push was needed/allowed.
    """
    cfg = {**entry.data, **entry.options}
    ohmigo_entity: str = cfg.get("ohmigo_entity", "")
    if not ohmigo_entity:
        return last_push_time

    if not _ohmigo_push_enabled(hass, entry.entry_id):
        return last_push_time

    # Throttle: honour user-configured minimum interval.
    interval_minutes: float = float(
        cfg.get("ohmigo_interval_minutes", OHMIGO_DEFAULT_INTERVAL_MINUTES)
    )
    now = dt_util.now()
    if last_push_time is not None:
        elapsed = (now - last_push_time).total_seconds() / 60.0
        if elapsed < interval_minutes:
            return last_push_time

    # Round to nearest 0.5 °C.
    new_val = round(fake_temp * 2) / 2

    # Hysteresis check.
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
        except (ValueError, TypeError):
            pass  # unavailable/unknown state — push anyway

    try:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": ohmigo_entity, "value": new_val},
            blocking=False,
        )
        _LOGGER.debug("Ohmigo push: %s → %.1f °C", ohmigo_entity, new_val)

        logbook.async_log_entry(
            hass,
            name="PumpSteer",
            message=f"Ohmigo push → {new_val} °C",
            domain=DOMAIN,
            entity_id=ohmigo_entity,
        )

        return now
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Ohmigo push failed for %s: %s", ohmigo_entity, err)
        return last_push_time
