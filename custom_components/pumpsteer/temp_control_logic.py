import logging

_LOGGER = logging.getLogger(__name__)

# 🟩 NYA KONSTANTER – SÄKERHETSGRÄNSER
MIN_FAKE_TEMP = -25.0
MAX_FAKE_TEMP = 30.0

def calculate_temperature_output(
    indoor_temp: float,
    actual_target_temp_for_logic: float,
    real_outdoor_temp: float,
    aggressiveness: float
) -> tuple[float, str]:
    """
    Calculates the virtual outdoor temperature (fake_temp) and operating mode
    based on indoor temperature and target temperature.
    """

    # Validera indata
    if not all(isinstance(x, (int, float)) for x in [indoor_temp, actual_target_temp_for_logic, real_outdoor_temp, aggressiveness]):
        _LOGGER.error("Invalid input types for temperature calculation")
        return real_outdoor_temp, "error"

    # Begränsa aggressivitet mellan 0–5
    aggressiveness = max(0, min(5, aggressiveness))
    diff = indoor_temp - actual_target_temp_for_logic

    # ➤ PASSTHROUGH (Aggressiveness = 0)
    if aggressiveness == 0:
        fake_temp = real_outdoor_temp
        mode = "passthrough"
        _LOGGER.debug(f"TempControl: Passthrough (fake temp: {fake_temp:.1f} °C) - Mode: {mode}")
        return fake_temp, mode

    # ➤ SKALNING VID AGGRESSIVITET
    scaling_factor = aggressiveness * 0.1
    fake_temp = 0.0
    mode = "unknown"

    # ➤ HEATING-läge (för kallt inne)
    if diff < -0.5:
        fake_temp = real_outdoor_temp + (diff * scaling_factor * 2)
        # 🟥 Tidigare: fake_temp = max(min(fake_temp, 30.0), -15.0)
        # 🟩 Nu: använd global säkerhetsgräns
        fake_temp = max(min(fake_temp, MAX_FAKE_TEMP), MIN_FAKE_TEMP)
        mode = "heating"
        _LOGGER.debug(f"TempControl: Heating (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}")

    # ➤ BRAKING-läge (för varmt inne)
    elif diff > 0.5:
        fake_temp = real_outdoor_temp + (diff * scaling_factor * 4)
        # 🟥 Tidigare: fake_temp = max(fake_temp, 25.0)
        # 🟩 Nu: begränsa inom 25.0 och MAX_FAKE_TEMP
        fake_temp = max(min(fake_temp, MAX_FAKE_TEMP), 25.0)
        mode = "braking_by_temp"
        _LOGGER.debug(f"TempControl: Braking (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}")

    # ➤ NEUTRAL-läge
    else:
        fake_temp = real_outdoor_temp
        mode = "neutral"
        _LOGGER.debug(f"TempControl: Within comfort zone (diff: {diff:.2f}) - Mode: {mode}")

    # ⚠️ EXTRA: logga om säkerhetsgräns träffas
    if fake_temp <= MIN_FAKE_TEMP or fake_temp >= MAX_FAKE_TEMP:
        _LOGGER.warning(f"TempControl: Fake temp reached safety limit: {fake_temp:.1f} °C")

    # 🟥 Tidigare: extra safety check (redundant)
    # fake_temp = max(min(fake_temp, 30.0), -25.0)

    return fake_temp, mode

# import logging

# _LOGGER = logging.getLogger(__name__)

# # 🟩 NYA KONSTANTER – SÄKERHETSGRÄNSER
# MIN_FAKE_TEMP = -25.0
# MAX_FAKE_TEMP = 30.0

# def calculate_temperature_output(
#     indoor_temp: float,
#     actual_target_temp_for_logic: float,
#     real_outdoor_temp: float,
#     aggressiveness: float
# ) -> tuple[float, str]:
#     """
#     Calculates the virtual outdoor temperature (fake_temp) and operating mode
#     based on indoor temperature and target temperature.

#     Args:
#         indoor_temp: Current indoor temperature
#         actual_target_temp_for_logic: Target temperature to use in logic
#         real_outdoor_temp: Actual outdoor temperature
#         aggressiveness: 0 (passthrough) to 5 (most aggressive, prioritizes savings)
    
#     Returns:
#         Tuple of (fake_temp, mode)
#     """
#     # Validate inputs
#     if not all(isinstance(x, (int, float)) for x in [indoor_temp, actual_target_temp_for_logic, real_outdoor_temp, aggressiveness]):
#         _LOGGER.error("Invalid input types for temperature calculation")
#         return real_outdoor_temp, "error"
    
#     # Ensure aggressiveness is within valid range
#     aggressiveness = max(0, min(5, aggressiveness))
    
#     diff = indoor_temp - actual_target_temp_for_logic
    
#     # Handle aggressiveness = 0 first, as it's a special passthrough mode.
#     if aggressiveness == 0:
#         fake_temp = real_outdoor_temp
#         mode = "passthrough"
#         _LOGGER.debug(f"TempControl: Passthrough (fake temp: {fake_temp:.1f} °C) - Mode: {mode}")
#         return fake_temp, mode

#     # For aggressiveness > 0, calculate scaling_factor based on aggressiveness.
#     scaling_factor = aggressiveness * 0.1

#     fake_temp = 0.0
#     mode = "unknown"

#     if diff < -0.5:  # Indoor is colder than target with a margin, signal for heating
#         # When indoor is too cold, decrease fake_temp significantly
#         fake_temp = real_outdoor_temp + (diff * scaling_factor * 2)
#         # Cap fake_temp to prevent unrealistic values
#         fake_temp = max(min(fake_temp, 30.0), -15.0)  # Uses 25.0 as upper cap
#         mode = "heating"
#         _LOGGER.debug(f"TempControl: Heating (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}")

#     elif diff > 0.5:  # Indoor is warmer than target with a margin, signal for braking
#         # When indoor is too warm, increase fake_temp significantly
#         fake_temp = real_outdoor_temp + (diff * scaling_factor * 4)
#         # Set a minimum floor for fake_temp to ensure clear "no heating" signal
#         fake_temp = max(fake_temp, 25.0) # Uses 25.0 as lower floor
#         mode = "braking_by_temp"
#         _LOGGER.debug(f"TempControl: Braking by temperature (fake temp: {fake_temp:.1f} °C, diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}")

#     else:  # Within the comfort zone (-0.5°C to +0.5°C), neutral mode
#         # In the comfort zone, maintain neutral state based on actual outdoor temperature
#         fake_temp = real_outdoor_temp # <-- Ändrad tillbaka till real_outdoor_temp
#         mode = "neutral"
#         _LOGGER.debug(f"TempControl: Within comfort deadband (diff: {diff:.2f}, agg: {aggressiveness}) - Mode: {mode}")

#     # Final safety check
#     fake_temp = max(min(fake_temp, 30.0), -25.0)  # Absolute safety bounds
    
#     return fake_temp, mode
