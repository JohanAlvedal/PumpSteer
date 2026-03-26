"""PumpSteer holiday mode logic."""

import logging
from datetime import datetime
from typing import Optional

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .notify import async_send_notification

_LOGGER = logging.getLogger(__name__)

CLEARED_YEAR = 1970


def _get_entity_ids(hass: HomeAssistant, entry_id: str) -> tuple:
    registry = er.async_get(hass)
    boolean = registry.async_get_entity_id(
        "switch", "pumpsteer", f"{entry_id}_holiday_mode"
    )
    start = registry.async_get_entity_id(
        "datetime", "pumpsteer", f"{entry_id}_holiday_start"
    )
    end = registry.async_get_entity_id(
        "datetime", "pumpsteer", f"{entry_id}_holiday_end"
    )
    return boolean, start, end


def _get_datetime(hass: HomeAssistant, entity_id: str) -> Optional[datetime]:
    if not entity_id:
        return None
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


def _is_boolean_on(hass: HomeAssistant, boolean_entity: str) -> bool:
    if not boolean_entity:
        return False
    state = hass.states.get(boolean_entity)
    return bool(state and state.state == "on")


async def _turn_boolean(hass: HomeAssistant, boolean_entity: str, on: bool) -> None:
    if not boolean_entity:
        return
    service = "turn_on" if on else "turn_off"
    await hass.services.async_call(
        "switch",
        service,
        {"entity_id": boolean_entity},
        blocking=True,
    )


async def _clear_dates(hass: HomeAssistant, start_entity: str, end_entity: str) -> None:
    for entity_id in (start_entity, end_entity):
        if not entity_id:
            continue
        await hass.services.async_call(
            "datetime",
            "set_value",
            {"entity_id": entity_id, "datetime": "1970-01-01T00:00:00+00:00"},
            blocking=True,
        )
    _LOGGER.debug("Holiday dates cleared")


async def async_update_holiday(
    hass: HomeAssistant, entry_id: str, entry: ConfigEntry
) -> bool:
    """Called every sensor update cycle. Returns True if holiday mode is active."""
    boolean_entity, start_entity, end_entity = _get_entity_ids(hass, entry_id)

    now = dt_util.now()
    boolean_on = _is_boolean_on(hass, boolean_entity)
    start_dt = _get_datetime(hass, start_entity)
    end_dt = _get_datetime(hass, end_entity)

    dates_valid = start_dt is not None and end_dt is not None and end_dt > start_dt

    if dates_valid and not boolean_on and now >= start_dt and now < end_dt:
        _LOGGER.info("Holiday mode: auto-activating (start time reached)")
        await _turn_boolean(hass, boolean_entity, True)
        await async_send_notification(
            hass,
            entry,
            "🏖️ Holiday mode activated",
            f"PumpSteer holiday mode is now active.\nHoliday ends: {end_dt.strftime('%d/%m/%Y %H:%M')}",
            notification_id="pumpsteer_holiday",
        )
        return True

    if boolean_on and dates_valid and now >= end_dt:
        _LOGGER.info("Holiday mode: auto-deactivating (end time reached)")
        await _turn_boolean(hass, boolean_entity, False)
        await _clear_dates(hass, start_entity, end_entity)
        await async_send_notification(
            hass,
            entry,
            "🏠 Holiday mode ended",
            "PumpSteer is back to normal operation.\nWelcome home!",
            notification_id="pumpsteer_holiday",
        )
        return False

    if boolean_on and not dates_valid:
        _LOGGER.debug("Holiday mode: manually active (no dates set)")
        return True

    if boolean_on and dates_valid and start_dt <= now < end_dt:
        return True

    if boolean_on and dates_valid and now < start_dt:
        _LOGGER.debug("Holiday mode: boolean ON but start not reached yet")
        return False

    return False
