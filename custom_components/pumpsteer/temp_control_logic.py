import logging

_LOGGER = logging.getLogger(__name__)

def calculate_temperature_output(
    indoor_temp: float,
    actual_target_temp_for_logic: float,
    real_outdoor_temp: float,
    aggressiveness: float
) -> tuple[float, str]:
    """
    Calculates the virtual outdoor temperature (fake_temp) and operating mode
    based on indoor temperature and target temperature.

    aggressiveness: 0 (passthrough) to 5 (most aggressive, prioritizes savings)
    """
    diff = indoor_temp - actual_target_temp_for_logic
    
    # Handle aggressiveness = 0 first, as it's a special passthrough mode.
    # In this mode, the sensor output (fake_temp) should simply reflect the real outdoor temperature.
    if aggressiveness == 0:
        fake_temp = real_outdoor_temp
        mode = "passthrough"
        _LOGGER.debug(f"TempControl: Passthrough (fake temp: {fake_temp:.1f} °C) - Mode: {mode}")
        return fake_temp, mode

    # For aggressiveness > 0, calculate scaling_factor based on aggressiveness.
    # A higher aggressiveness value will result in a larger scaling_factor,
    # leading to more pronounced adjustments of fake_temp.
    # The multiplier 0.1 ensures that aggressiveness 5 results in a scaling_factor of 0.5.
    scaling_factor = aggressiveness * 0.1 #

    fake_temp = 0.0  # Initialize to ensure it always gets a value
    mode = "unknown"  # Initialize mode

    if diff < -0.5:  # Indoor is colder than target with a margin, signal for heating
        # When indoor is too cold, we want to decrease fake_temp significantly
        # to make the heat pump work harder. The 'diff' is negative here.
        # Multiplying by 2 amplifies the effect for heating.
        fake_temp = real_outdoor_temp + (diff * scaling_factor * 2) #
        # Cap fake_temp to 20.0 to prevent it from going unrealistically high
        # and to ensure a clear heating signal.
        fake_temp = min(fake_temp, 20.0) #
        mode = "heating" #
        _LOGGER.debug(f"TempControl: Heating (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}") #

    elif diff > 0.5:  # Indoor is warmer than target with a margin, signal for braking
        # When indoor is too warm, we want to increase fake_temp significantly
        # to make the heat pump work less or even stop. The 'diff' is positive here.
        # Multiplying by 4 amplifies the effect for braking, making it more aggressive.
        fake_temp = real_outdoor_temp + (diff * scaling_factor * 4) #
        # Set a minimum floor for fake_temp at 20.0 to ensure a clear "no heating" signal.
        fake_temp = max(fake_temp, 20.0) #
        mode = "braking_by_temp" #
        _LOGGER.debug(f"TempControl: Braking by temperature (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}") #

    else:  # Within the comfort zone (-0.5°C to +0.5°C), neutral mode
        # In the comfort zone, the system aims to maintain the current temperature
        # without aggressive heating or braking. A fake_temp of 20.0°C typically
        # indicates a neutral state for heat pumps (no active heating needed).
        fake_temp = 20.0 #
        mode = "neutral" #
        _LOGGER.debug(f"TempControl: Within comfort deadband (diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}") #

    return fake_temp, mode #
