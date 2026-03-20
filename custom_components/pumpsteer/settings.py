from typing import List, Final
import logging

_LOGGER = logging.getLogger(__name__)

PUMPSTEER_VERSION: Final[str] = "1.2.1"
DEFAULT_HOUSE_INERTIA: Final[float] = 1.0
BRAKING_MODE_TEMP: Final[float] = 19.0
AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.5

MIN_FAKE_TEMP: Final[float] = -25.0
MAX_FAKE_TEMP: Final[float] = 25.0
BRAKE_FAKE_TEMP: Final[float] = 25.0
PRECOOL_LOOKAHEAD: Final[int] = 24
PRECOOL_MARGIN: Final[float] = 3.0
WINTER_BRAKE_TEMP_OFFSET: Final[float] = 10.0
WINTER_BRAKE_THRESHOLD: Final[float] = 7.0
CHEAP_PRICE_OVERSHOOT: Final[float] = 1.5
PID_KP: Final[float] = 2.4
PID_KI: Final[float] = 0.035
PID_KD: Final[float] = 0.0
PID_INTEGRAL_CLAMP: Final[float] = 6.0
PID_OUTPUT_CLAMP: Final[float] = 12.0
PID_INTEGRATOR_ON_BRAKE: Final[str] = "freeze"
PID_DECAY_PER_MINUTE_ON_BRAKE: Final[float] = 0.98
BRAKE_RAMP_IN_MINUTES: Final[float] = 15.0
BRAKE_RAMP_OUT_MINUTES: Final[float] = 15.0
MIN_BRAKE_STRENGTH: Final[float] = 0.0
MAX_BRAKE_STRENGTH: Final[float] = 1.0
HEATING_COMPENSATION_FACTOR: Final[float] = 0.2
BRAKING_COMPENSATION_FACTOR: Final[float] = 0.4
HEATING_THRESHOLD: Final[float] = -1.5

DEFAULT_PERCENTILES: Final[List[int]] = [10, 30, 85, 95]
DEFAULT_EXTREME_MULTIPLIER: Final[float] = 1.5
MIN_SAMPLES_FOR_CLASSIFICATION: Final[int] = 5

PRICE_CATEGORIES: Final[List[str]] = [
    "very_cheap",
    "cheap",
    "normal",
    "expensive",
    "very_expensive",
    "extreme",
]

ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.60
DEFAULT_TRAILING_HOURS: Final[int] = 72
MAX_PRICE_WARNING_THRESHOLD: Final[float] = 3.0

VERY_CHEAP_MULTIPLIER: Final[float] = 0.60
CHEAP_MULTIPLIER: Final[float] = 0.90
NORMAL_MULTIPLIER: Final[float] = 1.40
EXPENSIVE_MULTIPLIER: Final[float] = 2.00
VERY_EXPENSIVE_MULTIPLIER: Final[float] = 3.00

MIN_REASONABLE_TEMP: Final[float] = -50.0
MAX_REASONABLE_TEMP: Final[float] = 50.0
MIN_REASONABLE_PRICE: Final[float] = -2.0
MAX_REASONABLE_PRICE: Final[float] = 15.0


def validate_core_settings() -> None:
    errors = []

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
