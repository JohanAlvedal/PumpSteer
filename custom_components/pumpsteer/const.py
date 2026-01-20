"""Constants for the PumpSteer integration."""

from typing import Final, List, Optional

DOMAIN: Final[str] = "pumpsteer"
DATA_VERSION: Final[str] = "version"

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

# === PI CONTROL SETTINGS ===
PRICE_PI_KP: Final[float] = 0.12
PRICE_PI_KI: Final[float] = 0.04
PRICE_HORIZON_STEPS_15M: Final[int] = 8
PRICE_HORIZON_STEPS_HOURLY: Final[int] = 6
PRICE_MAX_DELTA_PER_STEP: Final[float] = 0.08
PRICE_BRAKE_MAX_DELTA_PER_STEP: Final[float] = 0.08
MPC_HORIZON_STEPS: Final[int] = 6
MPC_PRICE_WEIGHT: Final[float] = 1.0
MPC_COMFORT_WEIGHT: Final[float] = 1.0
MPC_SMOOTH_WEIGHT: Final[float] = 1.0

# === PRICE BRAKE BLOCK SETTINGS ===
MIN_BLOCK_DURATION_MIN: Final[int] = 60
PRICE_BLOCK_THRESHOLD_DELTA: Final[float] = 0.3
PRICE_BLOCK_THRESHOLD_PERCENTILE: Final[Optional[float]] = None
PRICE_BRAKE_PRE_MINUTES: Final[int] = 60
PRICE_BRAKE_POST_MINUTES: Final[int] = 60
PRICE_BLOCK_AREA_SCALE: Final[float] = 4.0
EXTREME_PRICE_BRAKE_OVERRIDE_PERCENTILE: Final[float] = 0.95
EXTREME_PRICE_MAX_DEFICIT_ALLOW_BRAKE_C: Final[float] = 1.0

COMFORT_PI_KP: Final[float] = 0.6
COMFORT_PI_KI: Final[float] = 0.1
COMFORT_DEADBAND: Final[float] = 0.1

BRAKE_WEIGHT: Final[float] = 1.0
GAS_WEIGHT: Final[float] = 0.8
COMFORT_BACKOFF_WEIGHT: Final[float] = 0.5
CONTROL_BIAS_TEMP_SCALE: Final[float] = 1.5

# === COMFORT CONTROL SETTINGS ===
# Defines when the system considers the indoor temperature "too cold"
# to allow price braking. Previously hardcoded as -0.5 °C inside the logic.
#
# If target_temp - indoor_temp > abs(HEATING_THRESHOLD):
#     → PumpSteer enters heating mode regardless of price.
#
# Increasing the value to -1.0 or -1.5 allows more price braking
# even when the house is below the target temperature.

HEATING_THRESHOLD: Final[float] = -1.5  # °C

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
