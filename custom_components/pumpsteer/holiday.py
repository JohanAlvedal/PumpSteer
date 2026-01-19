from datetime import datetime
import logging
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import parse_datetime
from homeassistant.const import STATE_ON
from .const import HOLIDAY_TEMP

_LOGGER = logging.getLogger(__name__)


def is_holiday_mode_active(
    hass: HomeAssistant,
    holiday_mode_boolean_entity_id: str | None,
    holiday_start_datetime_entity_id: str | None,
    holiday_end_datetime_entity_id: str | None,
) -> bool:
    """
    Checks if the current time falls within the defined holiday period AND if the boolean switch is ON.
    When active, the target temperature should be set to HOLIDAY_TEMP.
    Args:
        hass: The Home Assistant instance.
        holiday_mode_boolean_entity_id: The entity ID for the holiday mode boolean switch
                                        (e.g., input_boolean.pumpsteer_holiday_mode).
                                        If None, this check is skipped (see important note below).
        holiday_start_datetime_entity_id: The entity ID for the holiday start datetime
                                          (e.g., input_datetime.pumpsteer_holiday_start).
        holiday_end_datetime_entity_id: The entity ID for the holiday end datetime
                                        (e.g., input_datetime.pumpsteer_holiday_end).

    Returns:
        True if holiday mode is active, False otherwise.
    """
    # check the boolean entity first (if configured)
    if holiday_mode_boolean_entity_id:
        boolean_state = hass.states.get(holiday_mode_boolean_entity_id)

        if not boolean_state or boolean_state.state != STATE_ON:
            _LOGGER.debug(
                "[PumpSteer - Holiday] Holiday mode boolean (%s) is not ON. State: %s",
                holiday_mode_boolean_entity_id,
                boolean_state.state if boolean_state else "N/A",
            )
            return False
    else:
        _LOGGER.debug(
            "[PumpSteer - Holiday] Holiday mode boolean entity not configured. Skipping boolean check."
        )

    if not holiday_start_datetime_entity_id or not holiday_end_datetime_entity_id:
        _LOGGER.debug(
            "[PumpSteer - Holiday] Holiday datetime entities not configured. Holiday mode inactive."
        )
        return False

    holiday_start_state = hass.states.get(holiday_start_datetime_entity_id)
    holiday_end_state = hass.states.get(holiday_end_datetime_entity_id)

    if not holiday_start_state or not holiday_end_state:
        _LOGGER.debug(
            "[PumpSteer - Holiday] Holiday datetime entities not available: "
            "Start: %s (%s), "
            "End: %s (%s)",
            holiday_start_datetime_entity_id,
            holiday_start_state,
            holiday_end_datetime_entity_id,
            holiday_end_state,
        )
        return False

    try:
        holiday_start_time = parse_datetime(holiday_start_state.state)
        holiday_end_time = parse_datetime(holiday_end_state.state)
    except ValueError as e:
        _LOGGER.warning(
            "[PumpSteer - Holiday] Error parsing holiday datetime states. "
            "Start state: '%s', End state: '%s', Error: %s",
            holiday_start_state.state,
            holiday_end_state.state,
            e,
        )
        return False

    current_time = datetime.now(holiday_start_time.tzinfo)

    if holiday_start_time is None or holiday_end_time is None:
        _LOGGER.warning(
            "[PumpSteer - Holiday] Could not parse holiday datetime states. "
            "Start state: '%s', End state: '%s'",
            holiday_start_state.state,
            holiday_end_state.state,
        )
        return False

    if holiday_start_time <= current_time <= holiday_end_time:
        _LOGGER.debug(
            "[PumpSteer - Holiday] Holiday mode active (date range). Current: %s, "
            "Start: %s, End: %s. Using target temperature %s°C",
            current_time,
            holiday_start_time,
            holiday_end_time,
            HOLIDAY_TEMP,
        )
        return True

    _LOGGER.debug(
        "[PumpSteer - Holiday] Holiday mode inactive (date range). Current: %s, "
        "Start: %s, End: %s",
        current_time,
        holiday_start_time,
        holiday_end_time,
    )
    return False
