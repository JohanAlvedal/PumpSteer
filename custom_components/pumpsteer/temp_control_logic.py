import logging

from .settings import (
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
)

_LOGGER = logging.getLogger(__name__)


def calculate_temperature_output(
    indoor_temp: float,
    actual_target_temp_for_logic: float,
    real_outdoor_temp: float,
    aggressiveness: float,
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
                                the system should react to temperature differences.

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
            f"TempControl: Passthrough (fake temp: {fake_temp:.1f} °C) - Mode: {mode}"
        )
        return fake_temp, mode

    # SCALING WITH AGGRESSIVENESS
    scaling_factor = aggressiveness * 0.1
    fake_temp = 0.0
    mode = "aggressiveness"

    # HEATING mode (too cold indoors)
    # If indoor temperature is significantly below target, activate heating.
    # The fake temperature is reduced to make the heat pump work harder.
    if diff < -0.5:
        fake_temp = real_outdoor_temp + (diff * scaling_factor * 2)
        # Previously: fake_temp = max(min(fake_temp, 30.0), -15.0)
        # Now: use global safety limits
        fake_temp = max(min(fake_temp, MAX_FAKE_TEMP), MIN_FAKE_TEMP)
        mode = "heating"
        _LOGGER.debug(
            f"TempControl: Heating (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}"
        )

    # BRAKING mode (too warm indoors)
    # If indoor temperature is significantly above target, activate braking.
    # The fake temperature is increased to make the heat pump work less (or cool).
    elif diff > 0.5:
        fake_temp = real_outdoor_temp + (diff * scaling_factor * 4)
        fake_temp = max(min(fake_temp, MAX_FAKE_TEMP), brake_temp)
        mode = "braking_by_temp"
        _LOGGER.debug(
            f"TempControl: Braking (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}"
        )

    # NEUTRAL mode
    # If indoor temperature is within the comfort zone of the target, remain neutral.
    # The fake temperature is the real outdoor temperature.
    else:
        fake_temp = real_outdoor_temp
        mode = "neutral"
        _LOGGER.debug(
            f"TempControl: Within comfort zone (diff: {diff:.2f}) - Mode: {mode}"
        )

    # EXTRA: log if safety limit is hit
    if fake_temp <= MIN_FAKE_TEMP or fake_temp >= MAX_FAKE_TEMP:
        _LOGGER.warning(
            f"TempControl: Fake temp reached safety limit: {fake_temp:.1f} °C (Mode: {mode})"
        )

    return fake_temp, mode
