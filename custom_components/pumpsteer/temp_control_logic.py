import logging

from .settings import (
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
    HEATING_COMPENSATION_FACTOR,
    BRAKING_COMPENSATION_FACTOR,
    HEATING_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


def calculate_temperature_output(
    indoor_temp: float,
    actual_target_temp_for_logic: float,
    real_outdoor_temp: float,
    aggressiveness: float,
    integral_error: float,
    integral_gain: float,
    brake_temp: float,
) -> tuple[float, str]:
    """
    Calculates the virtual outdoor temperature (fake_temp) and operating mode
    based on indoor temperature and target temperature.

    Args:
        indoor_temp (float): The current indoor temperature.
        actual_target_temp_for_logic (float): The target temperature for the logic.
        real_outdoor_temp (float): The actual outdoor temperature.
        aggressiveness (float): A value between 0 and 5 indicating how aggressively
                                the system should brake based on temperature surplus.
        integral_error (float): Accumulated temperature error for PI-style heating.
        integral_gain (float): Gain applied to the accumulated error for heating.

    Returns:
        tuple[float, str]: A tuple containing the calculated fake outdoor temperature
                           and the operating mode ("passthrough", "heating", "braking_by_temp", "neutral", "error").
    """

    # Validate input types
    if not all(
        isinstance(x, (int, float))
        for x in [
            indoor_temp,
            actual_target_temp_for_logic,
            real_outdoor_temp,
            aggressiveness,
            integral_error,
            integral_gain,
        ]
    ):
        _LOGGER.error("Invalid input types for temperature calculation")
        return real_outdoor_temp, "error"

    # Limit aggressiveness between 0–5
    aggressiveness = max(0, min(5, aggressiveness))
    diff = indoor_temp - actual_target_temp_for_logic

    # PASSTHROUGH (Aggressiveness = 0)
    # If aggressiveness is 0, the system operates in passthrough mode,
    # meaning the fake temperature is simply the real outdoor temperature.
    if aggressiveness == 0:
        fake_temp = real_outdoor_temp
        mode = "passthrough"
        _LOGGER.debug(
            "TempControl: Passthrough (fake temp: %.1f °C) - Mode: %s",
            fake_temp,
            mode,
        )
        return fake_temp, mode

    # Default to neutral behaviour
    fake_temp = real_outdoor_temp
    mode = "neutral"

    # HEATING mode (too cold indoors)
    # If indoor temperature is significantly below target, activate heating.
    # The fake temperature is reduced to make the heat pump work harder.
    if diff < HEATING_THRESHOLD:
        pi_adjustment = (diff * HEATING_COMPENSATION_FACTOR) + (
            integral_error * integral_gain
        )
        fake_temp += pi_adjustment

        fake_temp = max(min(fake_temp, MAX_FAKE_TEMP), MIN_FAKE_TEMP)
        mode = "heating"
        _LOGGER.debug(
            "TempControl: Heating (fake temp: %.1f °C, diff: %.2f, integral: %.2f, gain: %.2f) - Mode: %s",
            fake_temp,
            diff,
            integral_error,
            integral_gain,
            mode,
        )

    # BRAKING mode (too warm indoors)
    # If indoor temperature is significantly above target, activate braking.
    # The fake temperature is increased to make the heat pump work less (or cool).
    elif diff > 0.5:
        fake_temp += diff * aggressiveness * BRAKING_COMPENSATION_FACTOR
        brake_cap = max(min(brake_temp, MAX_FAKE_TEMP), MIN_FAKE_TEMP)
        fake_temp = brake_cap
        mode = "braking_by_temp"
        _LOGGER.debug(
            "TempControl: Braking (fake temp: %.1f °C, diff: %.2f, agg: %.1f) - Mode: %s",
            fake_temp,
            diff,
            aggressiveness,
            mode,
        )

    else:
        _LOGGER.debug(
            "TempControl: Within comfort zone (diff: %.2f) - Mode: %s",
            diff,
            mode,
        )

    if fake_temp <= MIN_FAKE_TEMP or fake_temp >= MAX_FAKE_TEMP:
        _LOGGER.warning(
            "TempControl: Fake temp reached safety limit: %.1f °C (Mode: %s)",
            fake_temp,
            mode,
        )

    return fake_temp, mode
