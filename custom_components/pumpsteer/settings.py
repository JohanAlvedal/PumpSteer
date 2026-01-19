"""Compatibility settings module for PumpSteer."""

import logging

from .const import (
    ABSOLUTE_CHEAP_LIMIT,
    AGGRESSIVENESS_SCALING_FACTOR,
    BRAKE_FAKE_TEMP,
    BRAKE_WEIGHT,
    BRAKING_COMPENSATION_FACTOR,
    BRAKING_MODE_TEMP,
    CHEAP_MULTIPLIER,
    CHEAP_PRICE_OVERSHOOT,
    COMFORT_BACKOFF_WEIGHT,
    COMFORT_DEADBAND,
    COMFORT_PI_KI,
    COMFORT_PI_KP,
    CONTROL_BIAS_TEMP_SCALE,
    DEFAULT_EXTREME_MULTIPLIER,
    DEFAULT_HOUSE_INERTIA,
    DEFAULT_PERCENTILES,
    DEFAULT_TRAILING_HOURS,
    EXPENSIVE_MULTIPLIER,
    GAS_WEIGHT,
    HARDCODED_ENTITIES,
    HEATING_COMPENSATION_FACTOR,
    HEATING_THRESHOLD,
    HOLIDAY_TEMP,
    MAX_FAKE_TEMP,
    MAX_PRICE_WARNING_THRESHOLD,
    MAX_REASONABLE_PRICE,
    MAX_REASONABLE_TEMP,
    MIN_BLOCK_DURATION_MIN,
    MIN_FAKE_TEMP,
    MIN_REASONABLE_PRICE,
    MIN_REASONABLE_TEMP,
    MIN_SAMPLES_FOR_CLASSIFICATION,
    MPC_COMFORT_WEIGHT,
    MPC_HORIZON_STEPS,
    MPC_PRICE_WEIGHT,
    MPC_SMOOTH_WEIGHT,
    NORMAL_MULTIPLIER,
    PRECOOL_LOOKAHEAD,
    PRECOOL_MARGIN,
    PRICE_BLOCK_AREA_SCALE,
    PRICE_BLOCK_THRESHOLD_DELTA,
    PRICE_BLOCK_THRESHOLD_PERCENTILE,
    PRICE_BRAKE_MAX_DELTA_PER_STEP,
    PRICE_BRAKE_POST_MINUTES,
    PRICE_BRAKE_PRE_MINUTES,
    PRICE_CATEGORIES,
    PRICE_HORIZON_STEPS_15M,
    PRICE_HORIZON_STEPS_HOURLY,
    PRICE_MAX_DELTA_PER_STEP,
    PRICE_PI_KI,
    PRICE_PI_KP,
    PUMPSTEER_VERSION,
    VERY_CHEAP_MULTIPLIER,
    VERY_EXPENSIVE_MULTIPLIER,
    WINTER_BRAKE_TEMP_OFFSET,
    WINTER_BRAKE_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "ABSOLUTE_CHEAP_LIMIT",
    "AGGRESSIVENESS_SCALING_FACTOR",
    "BRAKE_FAKE_TEMP",
    "BRAKE_WEIGHT",
    "BRAKING_COMPENSATION_FACTOR",
    "BRAKING_MODE_TEMP",
    "CHEAP_MULTIPLIER",
    "CHEAP_PRICE_OVERSHOOT",
    "COMFORT_BACKOFF_WEIGHT",
    "COMFORT_DEADBAND",
    "COMFORT_PI_KI",
    "COMFORT_PI_KP",
    "CONTROL_BIAS_TEMP_SCALE",
    "DEFAULT_EXTREME_MULTIPLIER",
    "DEFAULT_HOUSE_INERTIA",
    "DEFAULT_PERCENTILES",
    "DEFAULT_TRAILING_HOURS",
    "EXPENSIVE_MULTIPLIER",
    "GAS_WEIGHT",
    "HARDCODED_ENTITIES",
    "HEATING_COMPENSATION_FACTOR",
    "HEATING_THRESHOLD",
    "HOLIDAY_TEMP",
    "MAX_FAKE_TEMP",
    "MAX_PRICE_WARNING_THRESHOLD",
    "MAX_REASONABLE_PRICE",
    "MAX_REASONABLE_TEMP",
    "MIN_BLOCK_DURATION_MIN",
    "MIN_FAKE_TEMP",
    "MIN_REASONABLE_PRICE",
    "MIN_REASONABLE_TEMP",
    "MIN_SAMPLES_FOR_CLASSIFICATION",
    "MPC_COMFORT_WEIGHT",
    "MPC_HORIZON_STEPS",
    "MPC_PRICE_WEIGHT",
    "MPC_SMOOTH_WEIGHT",
    "NORMAL_MULTIPLIER",
    "PRECOOL_LOOKAHEAD",
    "PRECOOL_MARGIN",
    "PRICE_BLOCK_AREA_SCALE",
    "PRICE_BLOCK_THRESHOLD_DELTA",
    "PRICE_BLOCK_THRESHOLD_PERCENTILE",
    "PRICE_BRAKE_MAX_DELTA_PER_STEP",
    "PRICE_BRAKE_POST_MINUTES",
    "PRICE_BRAKE_PRE_MINUTES",
    "PRICE_CATEGORIES",
    "PRICE_HORIZON_STEPS_15M",
    "PRICE_HORIZON_STEPS_HOURLY",
    "PRICE_MAX_DELTA_PER_STEP",
    "PRICE_PI_KI",
    "PRICE_PI_KP",
    "PUMPSTEER_VERSION",
    "VERY_CHEAP_MULTIPLIER",
    "VERY_EXPENSIVE_MULTIPLIER",
    "WINTER_BRAKE_TEMP_OFFSET",
    "WINTER_BRAKE_THRESHOLD",
]


def validate_core_settings() -> None:
    """Validate core settings for consistency and logical values."""
    errors = []

    # Validate percentiles
    if len(DEFAULT_PERCENTILES) != 4:
        errors.append("Exactly 4 percentiles required for 5-category classification")

    if not all(0 <= p <= 100 for p in DEFAULT_PERCENTILES):
        errors.append("Percentiles must be between 0 and 100")

    if DEFAULT_PERCENTILES != sorted(DEFAULT_PERCENTILES):
        errors.append("Percentiles must be in ascending order")

    if len(PRICE_CATEGORIES) != 6:
        errors.append("Exactly 6 price categories required (including 'extreme')")

    if MIN_FAKE_TEMP >= MAX_FAKE_TEMP:
        errors.append("Min fake temp must be less than max fake temp")

    multipliers = [
        VERY_CHEAP_MULTIPLIER,
        CHEAP_MULTIPLIER,
        NORMAL_MULTIPLIER,
        EXPENSIVE_MULTIPLIER,
        VERY_EXPENSIVE_MULTIPLIER,
    ]
    if multipliers != sorted(multipliers):
        errors.append("Price multipliers must be in ascending order")

    if VERY_EXPENSIVE_MULTIPLIER > 5.0:
        errors.append("VERY_EXPENSIVE_MULTIPLIER seems unreasonably high (>5.0)")

    if MIN_REASONABLE_TEMP >= MAX_REASONABLE_TEMP:
        errors.append("Min reasonable temp must be less than max reasonable temp")

    if MIN_REASONABLE_PRICE >= MAX_REASONABLE_PRICE:
        errors.append("Min reasonable price must be less than max reasonable price")

    if ABSOLUTE_CHEAP_LIMIT <= 0:
        errors.append("ABSOLUTE_CHEAP_LIMIT must be positive")

    if ABSOLUTE_CHEAP_LIMIT > 2.0:
        errors.append("ABSOLUTE_CHEAP_LIMIT seems unreasonably high (>2.0 SEK/kWh)")

    if errors:
        error_msg = f"Settings validation failed: {'; '.join(errors)}"
        _LOGGER.error(error_msg)
        raise ValueError(error_msg)


try:
    validate_core_settings()
    _LOGGER.debug(
        "PumpSteer core settings loaded successfully (version %s)",
        PUMPSTEER_VERSION,
    )
except Exception as e:
    _LOGGER.error("Failed to load PumpSteer settings: %s", e)
    raise
