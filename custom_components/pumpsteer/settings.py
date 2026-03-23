from typing import List, Final
import logging

_LOGGER = logging.getLogger(__name__)

PUMPSTEER_VERSION: Final[str] = "2.1.0"

# === FAKE TEMPERATURE LIMITS ===
MIN_FAKE_TEMP: Final[float] = -25.0
MAX_FAKE_TEMP: Final[float] = 25.0

# === SUMMER / PRECOOL ===
PRECOOL_LOOKAHEAD: Final[int] = 24
PRECOOL_MARGIN: Final[float] = 3.0
WINTER_BRAKE_TEMP_OFFSET: Final[float] = 10.0
WINTER_BRAKE_THRESHOLD: Final[float] = 7.0

# === PI CONTROLLER ===
PID_KP: Final[float] = 8.0
PID_KI: Final[float] = 0.05
PID_KD: Final[float] = 0.0
PID_INTEGRAL_CLAMP: Final[float] = 10.0
PID_OUTPUT_CLAMP: Final[float] = 20.0

# === PRICE CLASSIFICATION: P30/P80 against 72h history ===
# cheap  = below P30
# normal = P30 to P80
# expensive = above P80
PRICE_PERCENTILE_CHEAP: Final[float] = 30.0
PRICE_PERCENTILE_EXPENSIVE: Final[float] = 80.0
DEFAULT_TRAILING_HOURS: Final[int] = 72
MIN_SAMPLES_FOR_CLASSIFICATION: Final[int] = 5
ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.60   # SEK/kWh — always cheap regardless of history
MAX_PRICE_WARNING_THRESHOLD: Final[float] = 3.0

# === COMFORT FLOOR PER AGGRESSIVENESS ===
# How many °C below target each level tolerates before releasing the brake
# Index 0 = aggressiveness 0 (no price control), index 5 = max saving
COMFORT_FLOOR_BY_AGGRESSIVENESS: Final[List[float]] = [
    0.0,  # 0 — pure PI, no price logic
    0.2,  # 1 — very gentle
    0.5,  # 2 — mild
    0.9,  # 3 — normal / balanced
    1.4,  # 4 — aggressive
    2.0,  # 5 — maximum saving, can get cold
]

# === BRAKE DELTA ===
# How many °C above outdoor temp the fake temp is set during full braking.
# Higher = pump sees warmer "outdoor" = less heating output = harder braking.
# Typical: 10–15°C. 10°C is conservative, 15°C stops most pumps completely.
BRAKE_DELTA_C: Final[float] = 12.0

# === RAMP TIMING ===
# ramp_minutes = price_jump_ratio * house_inertia * RAMP_SCALE
# clamped between RAMP_MIN and RAMP_MAX
# ramp_minutes = price_jump_ratio * house_inertia * RAMP_SCALE
# With 15-min prices and inertia=3: 1 jump × 3 × 10 = 30 min = 2 price slots
RAMP_SCALE: Final[float] = 10.0
RAMP_MIN_MINUTES: Final[float] = 15.0   # at least 1 price slot (15-min prices)
RAMP_MAX_MINUTES: Final[float] = 60.0   # max 4 price slots

# Preheating: extra fake-temp depression during preheat window (°C)
PREHEAT_BOOST_C: Final[float] = 4.0

# Peak filter: ignore expensive spikes shorter than this
PEAK_FILTER_MIN_DURATION_MINUTES: Final[int] = 30

# How many hours ahead to scan for upcoming expensive periods
PRICE_LOOKAHEAD_HOURS: Final[int] = 6

# BRAKE HOLD TIME: keep brake active this many minutes after price drops
# to avoid rapid on/off cycling over short cheap dips within an expensive block.
# E.g. 30 min = holds brake across 2 cheap 15-min slots before releasing.
BRAKE_HOLD_MINUTES: Final[float] = 30.0

# === DEFAULTS ===
DEFAULT_SUMMER_THRESHOLD: Final[float] = 18.0
DEFAULT_AGGRESSIVENESS: Final[float] = 3.0
DEFAULT_HOUSE_INERTIA: Final[float] = 2.0
DEFAULT_TARGET_TEMP: Final[float] = 21.0
HOLIDAY_TEMP: Final[float] = 16.0

# === SANITY BOUNDS ===
MIN_REASONABLE_TEMP: Final[float] = -50.0
MAX_REASONABLE_TEMP: Final[float] = 50.0
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
