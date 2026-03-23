"""
PumpSteer holiday mode logic.

Replaces the yaml automations for holiday mode activate/deactivate/safety check.
Called from sensor.py on every update cycle.

Logic:
  - If boolean is manually ON and dates are set → check if within date range
  - If now() >= start and boolean is OFF → turn ON automatically
  - If now() >= end and boolean is ON  → turn OFF and clear dates
  - If boolean is ON but no dates set  → manual override, leave as-is
  - Safety: if boolean is ON and end has passed → turn OFF and clear dates
"""

import logging
from datetime import datetime
from typing import Optional

from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

BOOLEAN_ENTITY = "input_boolean.pumpsteer_holiday_mode"
START_ENTITY   = "input_datetime.pumpsteer_holiday_start"
END_ENTITY     = "input_datetime.pumpsteer_holiday_end"
CLEARED_YEAR   = 1970   # sentinel value meaning "no date set"


def _get_datetime(hass: HomeAssistant, entity_id: str) -> Optional[datetime]:
    """Read an input_datetime entity and return a timezone-aware datetime, or None."""
    state = hass.states.get(entity_id)
    if not state or state.state in ("unknown", "unavailable", ""):
        return None
    try:
        dt = dt_util.parse_datetime(state.state)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt_util.as_local(dt)
        if dt.year <= CLEARED_YEAR:
            return None
        return dt
    except (ValueError, TypeError):
        return None


def _is_boolean_on(hass: HomeAssistant) -> bool:
    state = hass.states.get(BOOLEAN_ENTITY)
    return bool(state and state.state == "on")


async def _turn_boolean(hass: HomeAssistant, on: bool) -> None:
    service = "turn_on" if on else "turn_off"
    # FIX 4: blocking=True så att state är uppdaterad innan vi returnerar
    await hass.services.async_call(
        "input_boolean",
        service,
        {"entity_id": BOOLEAN_ENTITY},
        blocking=True,
    )


async def _clear_dates(hass: HomeAssistant) -> None:
    """Reset both date fields to the sentinel 1970 value."""
    cleared = "1970-01-01 00:00:00"
    for entity_id in (START_ENTITY, END_ENTITY):
        # FIX 4: blocking=True så att datumen är rensade innan vi går vidare
        await hass.services.async_call(
            "input_datetime",
            "set_datetime",
            {"entity_id": entity_id, "datetime": cleared},
            blocking=True,
        )
    _LOGGER.debug("Holiday dates cleared")


async def _send_notification(hass: HomeAssistant, title: str, message: str) -> None:
    # Notiser behöver inte vara blocking — ordningen spelar ingen roll här
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": title, "message": message, "notification_id": "pumpsteer_holiday"},
        blocking=False,
    )


async def async_update_holiday(hass: HomeAssistant) -> bool:
    """
    Called every sensor update cycle. Handles all holiday activation/deactivation
    logic that would otherwise live in yaml automations.

    Returns True if holiday mode is currently active.
    """
    now        = dt_util.now()
    boolean_on = _is_boolean_on(hass)
    start_dt   = _get_datetime(hass, START_ENTITY)
    end_dt     = _get_datetime(hass, END_ENTITY)

    dates_valid = (
        start_dt is not None
        and end_dt is not None
        and end_dt > start_dt
    )

    # ── Case 1: Dates set, boolean OFF, start time reached → activate ─────────
    if dates_valid and not boolean_on and now >= start_dt and now < end_dt:
        _LOGGER.info("Holiday mode: auto-activating (start time reached)")
        await _turn_boolean(hass, True)
        await _send_notification(
            hass,
            "🏖️ Holiday mode activated",
            f"PumpSteer holiday mode is now active.\n"
            f"Holiday ends: {end_dt.strftime('%d/%m/%Y %H:%M')}",
        )
        return True

    # ── Case 2: Boolean ON, dates valid, end time reached → deactivate ────────
    if boolean_on and dates_valid and now >= end_dt:
        _LOGGER.info("Holiday mode: auto-deactivating (end time reached)")
        await _turn_boolean(hass, False)
        await _clear_dates(hass)
        await _send_notification(
            hass,
            "🏠 Holiday mode ended",
            "PumpSteer is back to normal operation.\nWelcome home!",
        )
        return False

    # ── Case 3: Boolean ON, no valid dates → manual override, stay active ─────
    if boolean_on and not dates_valid:
        _LOGGER.debug("Holiday mode: manually active (no dates set)")
        return True

    # ── Case 4: Boolean ON, dates valid, within window → active ───────────────
    if boolean_on and dates_valid and start_dt <= now < end_dt:
        return True

    # ── Case 5: Boolean ON, dates valid but not yet started → not active yet ──
    if boolean_on and dates_valid and now < start_dt:
        _LOGGER.debug("Holiday mode: boolean ON but start not reached yet")
        return False

    # ── Default: not active ────────────────────────────────────────────────────
    return False
