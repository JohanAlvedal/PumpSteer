# holiday.py
from datetime import datetime
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import as_datetime
from homeassistant.const import STATE_ON # Importera STATE_ON

_LOGGER = logging.getLogger(__name__)

# Konstanter
HOLIDAY_TARGET_TEMPERATURE = 16.0 # Grader Celsius

def is_holiday_mode_active(
    hass: HomeAssistant,
    holiday_mode_boolean_entity_id: str | None, # Ny parameter för input_boolean
    holiday_start_datetime_entity_id: str | None,
    holiday_end_datetime_entity_id: str | None
) -> bool:
    """
    Checks if the current time falls within the defined holiday period AND if the boolean switch is ON.

    Args:
        hass: The Home Assistant instance.
        holiday_mode_boolean_entity_id: The entity ID for the holiday mode boolean switch.
        holiday_start_datetime_entity_id: The entity ID for the holiday start datetime.
        holiday_end_datetime_entity_id: The entity ID for the holiday end datetime.

    Returns:
        True if holiday mode is active, False otherwise.
    """
    # 1. Kontrollera input_boolean
    if holiday_mode_boolean_entity_id:
        boolean_state = hass.states.get(holiday_mode_boolean_entity_id)
        if not boolean_state or boolean_state.state != STATE_ON:
            _LOGGER.debug(f"[PumpSteer - Holiday] Holiday mode boolean ({holiday_mode_boolean_entity_id}) is not ON. State: {boolean_state.state if boolean_state else 'N/A'}")
            return False # Inte aktivt om boolean inte är PÅ
    else:
        _LOGGER.debug("[PumpSteer - Holiday] Holiday mode boolean entity not configured. Skipping boolean check.")
        # Om boolean inte är konfigurerad, fortsätt och kontrollera bara datumintervallet.
        # Du kan ändra detta till att returnera False om du kräver att boolean ska vara konfigurerad.
        pass # Fortsätt för att kolla datumintervallet om boolean inte är konfigurerad

    # 2. Kontrollera datumintervall (befintlig logik)
    if not holiday_start_datetime_entity_id or not holiday_end_datetime_entity_id:
        _LOGGER.debug("[PumpSteer - Holiday] Holiday datetime entities not configured. Holiday mode inactive.")
        return False

    holiday_start_state = hass.states.get(holiday_start_datetime_entity_id)
    holiday_end_state = hass.states.get(holiday_end_datetime_entity_id)

    if not holiday_start_state or not holiday_end_state:
        _LOGGER.debug(
            f"[PumpSteer - Holiday] Holiday datetime entities not available: "
            f"Start: {holiday_start_datetime_entity_id} ({holiday_start_state}), "
            f"End: {holiday_end_datetime_entity_id} ({holiday_end_state})"
        )
        return False

    try:
        holiday_start_time = as_datetime(holiday_start_state.state)
        holiday_end_time = as_datetime(holiday_end_state.state)
        current_time = datetime.now(holiday_start_time.tzinfo)

        if holiday_start_time is None or holiday_end_time is None:
            _LOGGER.warning(
                f"[PumpSteer - Holiday] Could not parse holiday datetime states. "
                f"Start state: '{holiday_start_state.state}', End state: '{holiday_end_state.state}'"
            )
            return False

        if holiday_start_time <= current_time <= holiday_end_time:
            _LOGGER.debug(
                f"[PumpSteer - Holiday] Holiday mode active (date range). Current: {current_time}, "
                f"Start: {holiday_start_time}, End: {holiday_end_time}"
            )
            return True
        else:
            _LOGGER.debug(
                f"[PumpSteer - Holiday] Holiday mode inactive (date range). Current: {current_time}, "
                f"Start: {holiday_start_time}, End: {holiday_end_time}"
            )
            return False

    except Exception as e:
        _LOGGER.warning(
            f"[PumpSteer - Holiday] Error checking holiday mode date range: {e}. "
            f"Start state: '{holiday_start_state.state}', End state: '{holiday_end_state.state}'"
        )
        return False
