import logging
from typing import Final, List

_LOGGER = logging.getLogger(__name__)

PUMPSTEER_VERSION: Final[str] = "2.0.5"

# === FAKE TEMPERATURE LIMITS ===
MIN_FAKE_TEMP: Final[float] = -20.0
MAX_FAKE_TEMP: Final[float] = 25.0

# === SUMMER / PRECOOL SETTINGS ===
PRECOOL_LOOKAHEAD: Final[int] = 24
PRECOOL_MARGIN: Final[float] = 3.0
# These legacy constants are no longer used by sensor.py
# WINTER_BRAKE_TEMP_OFFSET: Final[float] = 10.0
# WINTER_BRAKE_THRESHOLD: Final[float] = 7.0

# === PI CONTROLLER ===
PID_KP: Final[float] = 2.4
PID_KI: Final[float] = 0.035
PID_KD: Final[float] = 0.0
PID_INTEGRAL_CLAMP: Final[float] = 6
PID_OUTPUT_CLAMP: Final[float] = 12

# === PRICE CLASSIFICATION ===
# Default thresholds use P30/P80 and a 72-hour trailing history window.
# cheap     = below P30
# normal    = P30 to P80
# expensive = above P80
PRICE_PERCENTILE_CHEAP: Final[float] = 30.0
PRICE_PERCENTILE_EXPENSIVE: Final[float] = 80.0
MIN_SAMPLES_FOR_CLASSIFICATION: Final[int] = 5
ABSOLUTE_CHEAP_LIMIT: Final[float] = (
    0.50  # SEK/kWh — always cheap regardless of history
)
MAX_PRICE_WARNING_THRESHOLD: Final[float] = 3.0

# Hybrid threshold weights.
# History gives stability across days.
# Horizon gives better adaptation to today's / tomorrow's price profile.
HISTORY_WEIGHT: Final[float] = 0.50
HORIZON_WEIGHT: Final[float] = 0.50

# === COMFORT FLOOR PER AGGRESSIVENESS ===
# How many °C below target each level tolerates before releasing the brake
# Index 0 = aggressiveness 0 (no price control), index 5 = max saving
COMFORT_FLOOR_BY_AGGRESSIVENESS: Final[List[float]] = [
    0.0,  # 0 — pure PI, no price logic
    0.5,  # 1 — very gentle
    1.0,  # 2 — mild
    1.5,  # 3 — normal / balanced
    2.0,  # 4 — aggressive
    3.0,  # 5 — maximum saving, can get cold
]

# === BRAKE TARGET OFFSET ===
# Full-brake target:
# fake outdoor temperature = real outdoor temperature + BRAKE_DELTA_C
# Higher value = stronger braking, because the heat pump sees a warmer outdoor temperature.
# Typical: 10–15°C. 10°C is conservative, while 15°C gives very strong braking
# for many heating systems.
BRAKE_DELTA_C: Final[float] = 10.0

# === RAMP TIMING ===
# Ramp duration scales with price-category jump severity and house inertia,
# then gets clamped between RAMP_MIN_MINUTES and RAMP_MAX_MINUTES.
# Example with 15-minute prices and inertia=3:
# 1 category jump × 3 × 10 = 30 minutes = 2 price slots
RAMP_SCALE: Final[float] = 10.0
RAMP_MIN_MINUTES: Final[float] = 20.0  # at least 1 price slot (15-min prices)
RAMP_MAX_MINUTES: Final[float] = 60.0  # max 4 price slots

# Preheating: extra boost applied during the preheat window (°C)
PREHEAT_BOOST_C: Final[float] = 4.0

# Peak filter: ignore expensive spikes shorter than this
PEAK_FILTER_MIN_DURATION_MINUTES: Final[int] = 30

# How many hours ahead to scan for upcoming expensive periods
PRICE_LOOKAHEAD_HOURS: Final[int] = 6

# BRAKE HOLD TIME: keep brake active this many minutes after price drops
# to avoid rapid on/off cycling over short cheap dips within an expensive block.
# E.g. 30 min = holds brake across 2 cheap 15-min slots before releasing.
BRAKE_HOLD_MINUTES: Final[float] = 30.0

# === PREHEATING FORECAST BEHAVIOR ===
# Controls what _forecast_is_cold() returns when the forecast entity has no data.
#
# False (default, recommended):
#   No preheating is triggered when forecast data is missing.
#   Safer behavior — avoids unnecessary preheating if the forecast entity is misconfigured.
#
# True:
#   Missing forecast data is treated as cold weather, so preheating may trigger.
#   This may be useful in climates where cold weather is the default assumption.
PREHEAT_ON_MISSING_FORECAST: Final[bool] = False

# === DEFAULTS ===
DEFAULT_SUMMER_THRESHOLD: Final[float] = 18.0
DEFAULT_AGGRESSIVENESS: Final[float] = 3.0
DEFAULT_HOUSE_INERTIA: Final[float] = 2.0
DEFAULT_TARGET_TEMP: Final[float] = 21.0
HOLIDAY_TEMP: Final[float] = 16.0

# === OHMIGO INTEGRATION ===
# Default minimum interval between pushes to the Ohmigo number entity.
# Users can override this per-installation in options (ohmigo_interval_minutes).
OHMIGO_DEFAULT_INTERVAL_MINUTES: Final[float] = 5.0

# Hysteresis: skip push when the new value is within this many °C of the current value.
OHMIGO_HYSTERESIS_C: Final[float] = 0.2

# === SANITY BOUNDS ===
MIN_REASONABLE_TEMP: Final[float] = -30.0
MAX_REASONABLE_TEMP: Final[float] = 30.0
MIN_REASONABLE_PRICE: Final[float] = -2.0
MAX_REASONABLE_PRICE: Final[float] = 15.0


def validate_core_settings() -> None:
    errors = []
    if MIN_FAKE_TEMP >= MAX_FAKE_TEMP:
        errors.append("MIN_FAKE_TEMP must be less than MAX_FAKE_TEMP")
    if len(COMFORT_FLOOR_BY_AGGRESSIVENESS) != 6:
        errors.append("COMFORT_FLOOR_BY_AGGRESSIVENESS must have 6 entries (0-5)")
    if not (0 < PRICE_PERCENTILE_CHEAP < PRICE_PERCENTILE_EXPENSIVE < 100):
        errors.append("Price percentiles must be 0 < P_cheap < P_expensive < 100")
    if RAMP_MIN_MINUTES >= RAMP_MAX_MINUTES:
        errors.append("RAMP_MIN_MINUTES must be less than RAMP_MAX_MINUTES")
    if BRAKE_DELTA_C <= 0:
        errors.append("BRAKE_DELTA_C must be positive")
    if BRAKE_HOLD_MINUTES < 0:
        errors.append("BRAKE_HOLD_MINUTES must be >= 0")
    if errors:
        msg = f"Settings validation failed: {'; '.join(errors)}"
        _LOGGER.error(msg)
        raise ValueError(msg)


validate_core_settings()
_LOGGER.debug("PumpSteer settings loaded (version %s)", PUMPSTEER_VERSION)
