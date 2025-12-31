import logging

from .settings import (
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
    HEATING_COMPENSATION_FACTOR,
    BRAKING_COMPENSATION_FACTOR,
    HEATING_THRESHOLD,
    MPC_HORIZON_STEPS,
    MPC_PRICE_WEIGHT,
    MPC_COMFORT_WEIGHT,
    MPC_SMOOTH_WEIGHT,
    MPC_HEATING_GAIN,
    MPC_MAX_STEP_DELTA,
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
        fake_temp += diff * aggressiveness * HEATING_COMPENSATION_FACTOR

        fake_temp = max(min(fake_temp, MAX_FAKE_TEMP), MIN_FAKE_TEMP)
        mode = "heating"
        _LOGGER.debug(
            "TempControl: Heating (fake temp: %.1f °C, diff: %.2f, agg: %.1f) - Mode: %s",
            fake_temp,
            diff,
            aggressiveness,
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


def calculate_mpc_temperature_output(
    indoor_temp: float,
    actual_target_temp_for_logic: float,
    real_outdoor_temp: float,
    aggressiveness: float,
    brake_temp: float,
    price_factor: float,
    inertia: float,
    previous_fake_temp: float,
    horizon_steps: int = MPC_HORIZON_STEPS,
    price_weight: float = MPC_PRICE_WEIGHT,
    comfort_weight: float = MPC_COMFORT_WEIGHT,
    smooth_weight: float = MPC_SMOOTH_WEIGHT,
) -> tuple[float, str]:
    """
    Calculates the virtual outdoor temperature using a simple MPC-inspired optimizer.

    Args:
        indoor_temp (float): The current indoor temperature.
        actual_target_temp_for_logic (float): The target temperature for the logic.
        real_outdoor_temp (float): The actual outdoor temperature.
        aggressiveness (float): A value between 0 and 5 indicating how aggressively
                                the system should react to temperature differences.
        brake_temp (float): Dynamic braking temperature cap.
        price_factor (float): Normalized price factor [0, 1].
        inertia (float): House inertia factor.
        previous_fake_temp (float): Previously applied fake temperature.
        horizon_steps (int): Number of steps to simulate ahead.
        price_weight (float): Weight for price cost.
        comfort_weight (float): Weight for comfort tracking.
        smooth_weight (float): Weight for smooth control changes.

    Returns:
        tuple[float, str]: A tuple containing the calculated fake outdoor temperature
                           and the operating mode ("mpc_heating", "mpc_braking", "mpc_neutral", "error").
    """

    if not all(
        isinstance(x, (int, float))
        for x in [
            indoor_temp,
            actual_target_temp_for_logic,
            real_outdoor_temp,
            aggressiveness,
            brake_temp,
            price_factor,
            inertia,
            previous_fake_temp,
        ]
    ):
        _LOGGER.error("Invalid input types for MPC temperature calculation")
        return real_outdoor_temp, "error"

    aggressiveness = max(0.0, min(5.0, aggressiveness))
    price_factor = max(0.0, min(1.0, price_factor))
    inertia = max(0.1, inertia)
    horizon_steps = max(1, horizon_steps)

    candidates = [
        real_outdoor_temp + delta
        for delta in [-MPC_MAX_STEP_DELTA, -1.5, -0.5, 0.0, 0.5, 1.5, MPC_MAX_STEP_DELTA]
    ]

    best_cost = float("inf")
    best_fake_temp = real_outdoor_temp

    for candidate in candidates:
        candidate = max(min(candidate, MAX_FAKE_TEMP), MIN_FAKE_TEMP)
        simulated_temp = indoor_temp
        total_cost = 0.0

        for step in range(horizon_steps):
            heating_push = (real_outdoor_temp - candidate) * MPC_HEATING_GAIN
            comfort_pull = (
                (actual_target_temp_for_logic - simulated_temp)
                * (aggressiveness / 5.0)
                / inertia
            )

            simulated_temp += heating_push + comfort_pull

            comfort_cost = abs(actual_target_temp_for_logic - simulated_temp)
            price_cost = price_factor * max(0.0, real_outdoor_temp - candidate)
            smooth_cost = abs(candidate - previous_fake_temp) if step == 0 else 0.0

            total_cost += (
                comfort_weight * comfort_cost
                + price_weight * price_cost
                + smooth_weight * smooth_cost
            )

        if total_cost < best_cost:
            best_cost = total_cost
            best_fake_temp = candidate

    best_fake_temp = min(best_fake_temp, brake_temp)
    best_fake_temp = max(min(best_fake_temp, MAX_FAKE_TEMP), MIN_FAKE_TEMP)

    diff = indoor_temp - actual_target_temp_for_logic
    if diff < HEATING_THRESHOLD:
        mode = "mpc_heating"
    elif diff > 0.5:
        mode = "mpc_braking"
    else:
        mode = "mpc_neutral"

    _LOGGER.debug(
        "TempControl: MPC (fake temp: %.1f °C, cost: %.2f, price_factor: %.2f) - Mode: %s",
        best_fake_temp,
        best_cost,
        price_factor,
        mode,
    )

    return best_fake_temp, mode
