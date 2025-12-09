from datetime import datetime
import logging
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import parse_datetime
from homeassistant.const import STATE_ON
from .settings import HOLIDAY_TEMP

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
    # 1. Check Holiday Mode Boolean Switch
    # This step ensures that Holiday Mode is explicitly enabled by the user via a Home Assistant helper entity (e.g., an input_boolean).
    if holiday_mode_boolean_entity_id:
        boolean_state = hass.states.get(holiday_mode_boolean_entity_id)
        # If the entity doesn't exist or its state is not 'on', holiday mode is not active.
        if not boolean_state or boolean_state.state != STATE_ON:
            _LOGGER.debug(
                "[PumpSteer - Holiday] Holiday mode boolean (%s) is not ON. State: %s",
                holiday_mode_boolean_entity_id,
                boolean_state.state if boolean_state else "N/A",
            )
            return False  # Not active if the boolean is not ON
    else:
        # Important Note: If the boolean entity ID is not provided (None),
        # this code will proceed to check only the date range.
        # Consider if you want to enforce that the boolean must always be configured and return False here if it's None.
        _LOGGER.debug(
            "[PumpSteer - Holiday] Holiday mode boolean entity not configured. Skipping boolean check."
        )
        pass  # Continue to check the date range if the boolean is not configured

    # 2. Check Date Range (Existing Logic)
    # This part verifies if both start and end datetime entities are configured.
    # If not, it's impossible to determine a holiday period.
    if not holiday_start_datetime_entity_id or not holiday_end_datetime_entity_id:
        _LOGGER.debug(
            "[PumpSteer - Holiday] Holiday datetime entities not configured. Holiday mode inactive."
        )
        return False

    holiday_start_state = hass.states.get(holiday_start_datetime_entity_id)
    holiday_end_state = hass.states.get(holiday_end_datetime_entity_id)

    # Check if the datetime entities actually exist and have states in Home Assistant.
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
        # Convert the entity states (which are strings) into datetime objects.
        # `parse_datetime` handles various datetime string formats and timezones.
        holiday_start_time = parse_datetime(holiday_start_state.state)
        holiday_end_time = parse_datetime(holiday_end_state.state)

        # Get the current time, ensuring it has the same timezone information as the holiday times
        # for accurate comparison.
        current_time = datetime.now(holiday_start_time.tzinfo)

        # If parsing failed (e.g., invalid date format in the entity state), log a warning and return False.
        if holiday_start_time is None or holiday_end_time is None:
            _LOGGER.warning(
                "[PumpSteer - Holiday] Could not parse holiday datetime states. "
                "Start state: '%s', End state: '%s'",
                holiday_start_state.state,
                holiday_end_state.state,
            )
            return False

        # Determine if the current time falls exactly within the defined start and end times.
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
        else:
            _LOGGER.debug(
                "[PumpSteer - Holiday] Holiday mode inactive (date range). Current: %s, "
                "Start: %s, End: %s",
                current_time,
                holiday_start_time,
                holiday_end_time,
            )
            return False

    except Exception as e:
        # Catch any unexpected errors during datetime parsing or comparison.
        _LOGGER.warning(
            "[PumpSteer - Holiday] Error checking holiday mode date range: %s. "
            "Start state: '%s', End state: '%s'",
            e,
            holiday_start_state.state,
            holiday_end_state.state,
        )
        return False
