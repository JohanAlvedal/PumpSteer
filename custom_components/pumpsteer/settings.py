from typing import List, Final
import logging

_LOGGER = logging.getLogger(__name__)

PUMPSTEER_VERSION: Final[str] = "1.2.1"
DEFAULT_HOUSE_INERTIA: Final[float] = 1.0
HOLIDAY_TEMP: Final[float] = 16.0
BRAKING_MODE_TEMP: Final[float] = 19.0
AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.5


MIN_FAKE_TEMP: Final[float] = -25.0
MAX_FAKE_TEMP: Final[float] = 25.0
BRAKE_FAKE_TEMP: Final[float] = 25.0
PRECOOL_LOOKAHEAD: Final[int] = 24  # Hours ahead to look for precooling
PRECOOL_MARGIN: Final[float] = 3.0  # °C margin added to summer threshold for precooling
WINTER_BRAKE_TEMP_OFFSET: Final[float] = (
    10.0  # °C offset above outdoor temp when braking in winter
)
WINTER_BRAKE_THRESHOLD: Final[float] = (
    7.0  # °C threshold for applying winter brake offset
)
CHEAP_PRICE_OVERSHOOT: Final[float] = (
    1.5  # °C to overshoot target when prices are very cheap
)
HEATING_COMPENSATION_FACTOR: Final[float] = (
    0.2  # Factor for lowering fake temp per °C deficit and aggressiveness unit
)
BRAKING_COMPENSATION_FACTOR: Final[float] = (
    0.4  # Factor for raising fake temp per °C surplus and aggressiveness unit
)

# === COMFORT CONTROL SETTINGS ===
# Defines when the system considers the indoor temperature "too cold"
# to allow price braking. Previously hardcoded as -0.5 °C inside the logic.
#
# If indoor_temp - target_temp < HEATING_THRESHOLD:
#     → PumpSteer enters heating mode regardless of price.
#
# Increasing the value to -1.0 or -1.5 allows more price braking
# even when the house is below the target temperature.

HEATING_THRESHOLD: Final[float] = -1.5  # °C

# === MPC SETTINGS ===
DEFAULT_CONTROL_MODE: Final[str] = "rule_based"
MPC_HORIZON_STEPS: Final[int] = 4
MPC_PRICE_WEIGHT: Final[float] = 0.5
MPC_COMFORT_WEIGHT: Final[float] = 1.0
MPC_SMOOTH_WEIGHT: Final[float] = 0.2
MPC_HEATING_GAIN: Final[float] = 0.15
MPC_MAX_STEP_DELTA: Final[float] = 2.0

# === ELECTRICITY PRICE CLASSIFICATION ===
DEFAULT_PERCENTILES: Final[List[int]] = [
    10,
    30,
    85,
    95,
]

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

ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.60  # SEK/kWh
DEFAULT_TRAILING_HOURS: Final[int] = 72  # Hours of historical data to consider
MAX_PRICE_WARNING_THRESHOLD: Final[float] = (
    3.0  # SEK/kWh - Log warning for extremely high prices
)


VERY_CHEAP_MULTIPLIER: Final[float] = 0.60
CHEAP_MULTIPLIER: Final[float] = 0.90
NORMAL_MULTIPLIER: Final[float] = 1.40
EXPENSIVE_MULTIPLIER: Final[float] = 2.00
VERY_EXPENSIVE_MULTIPLIER: Final[float] = 3.00

# === EXPLANATION OF DESIGN DECISIONS ===

# 1. EXTREME CATEGORY: YES
# - Prices over 300% of average get "extreme" classification
# - Useful for identifying truly exceptional price spikes
# - Helps differentiate between "very expensive" and "crisis level" pricing

# 2. ABSOLUTE_CHEAP_LIMIT: YES, KEEP AT 0.60 SEK/kWh
# - Still relevant as safety net for hybrid classification
# - Ensures that genuinely cheap absolute prices aren't missed
# - Example: If average is 2.00 SEK/kWh, 90% would be 1.80 SEK/kWh
#   But a price of 0.50 SEK/kWh should still be "cheap" regardless

# 3. HYBRID RULE: YES, KEEP IT
# - Allows absolute thresholds to override relative classification
# - Provides more intuitive results for users
# - Prevents situations where objectively cheap prices are classified as "normal"
#   just because the recent average was very low


MIN_REASONABLE_TEMP: Final[float] = -50.0
MAX_REASONABLE_TEMP: Final[float] = 50.0
MIN_REASONABLE_PRICE: Final[float] = -2.0  # SEK/kWh
MAX_REASONABLE_PRICE: Final[float] = 15.0  # SEK/kWh


def validate_core_settings() -> None:
    """Validate core settings for consistency and logical values"""
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
