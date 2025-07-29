from typing import List, Final

# === HOUSE CONTROL SETTINGS ===
DEFAULT_HOUSE_INERTIA: Final[float] = 1.0  # Default house thermal inertia

# === HOLIDAY MODE SETTINGS ===
HOLIDAY_TEMP: Final[float] = 16.0  # °C - Target temperature when holiday mode is active

# === TEMPERATURE CONTROL SETTINGS ===
BRAKING_MODE_TEMP: Final[float] = 22.5         # °C - Virtual outdoor temperature when braking due to high price
PREBOOST_OUTPUT_TEMP: Final[float] = -15.0     # °C - Virtual outdoor temperature when pre-boosting
NORMAL_MODE_MAX_OUTPUT_TEMP: Final[float] = 22.5  # °C - Max virtual outdoor temp in normal operation
NORMAL_MODE_MIN_OUTPUT_TEMP: Final[float] = -10.0  # °C - Min virtual outdoor temp in normal operation
AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.5  # Factor for aggressiveness in normal mode

# === ELECTRICITY PRICE CLASSIFICATION ===
DEFAULT_PERCENTILES: Final[List[int]] = [10, 30, 85, 95]  # Percentiles for 5-category classification
DEFAULT_EXTREME_MULTIPLIER: Final[float] = 1.5             # Multiplier for extreme price detection
MIN_SAMPLES_FOR_CLASSIFICATION: Final[int] = 5            # Minimum number of price samples needed
PRICE_CATEGORIES: Final[List[str]] = [                     # Price categories in ascending order
    "very_cheap", "cheap", "normal", "expensive", "very_expensive"
]
ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.50                 # SEK/kWh - Absolute threshold for cheap prices
DEFAULT_TRAILING_HOURS: Final[int] = 72                   # Hours of historical data to consider
MAX_PRICE_WARNING_THRESHOLD: Final[float] = 4.0           # SEK/kWh - Log warning for extremely high prices

# === HYBRID CLASSIFICATION THRESHOLDS ===
VERY_CHEAP_MULTIPLIER: Final[float] = 0.60    # 60% of average price
CHEAP_MULTIPLIER: Final[float] = 0.90         # 90% of average price  
NORMAL_MULTIPLIER: Final[float] = 1.15        # 115% of average price
EXPENSIVE_MULTIPLIER: Final[float] = 1.40     # 140% of average price

# === LEGACY PRICE THRESHOLD ===
HIGH_PRICE_THRESHOLD: Final[float] = 1.0       # SEK/kWh - Legacy threshold for temperature control

# === PRE-BOOST STRATEGY SETTINGS ===
COLD_HOUR_TEMP_THRESHOLD: Final[float] = 10.0  # °C - Max temperature for an hour to be considered "cold"
INERTIA_LEAD_TIME_FACTOR: Final[float] = 0.75
MIN_PRICE_THRESHOLD_RATIO: Final[float] = 0.5
MAX_PRICE_THRESHOLD_RATIO: Final[float] = 0.9
PREBOOST_AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.04
BASE_PRICE_THRESHOLD_RATIO: Final[float] = 0.9
MIN_LEAD_TIME: Final[float] = 0.5              # Hours
MAX_LEAD_TIME: Final[float] = 3.0              # Hours
PREBOOST_MAX_OUTDOOR_TEMP: Final[float] = 10.0  # °C - Max outdoor temp for pre-boost to be considered
MAX_PREBOOST_HOURS: Final[int] = 6             # How many hours ahead to look for pre-boost
PREBOOST_TEMP_THRESHOLD: Final[float] = 2.0    # °C - How many degrees colder than target to trigger pre-boost
PREBOOST_PRICE_THRESHOLD: Final[float] = 1.20  # SEK/kWh - Absolute price threshold for pre-boost

# === TEMPERATURE CONTROL LOGIC ===
MIN_FAKE_TEMP: Final[float] = -25.0
MAX_FAKE_TEMP: Final[float] = 30.0
BRAKE_FAKE_TEMP: Final[float] = 25.0
PUMPSTEER_INTEGRAL_GAIN: Final[float] = 0.05   # Adjustable, fine-tuned in Home Assistant


def validate_settings() -> None:
    """Validate that all settings are consistent and reasonable."""
    # Validate percentiles
    assert len(DEFAULT_PERCENTILES) == 4, "Exactly 4 percentiles required for 5-category classification"
    assert all(0 <= p <= 100 for p in DEFAULT_PERCENTILES), "Percentiles must be between 0 and 100"
    assert DEFAULT_PERCENTILES == sorted(DEFAULT_PERCENTILES), "Percentiles must be in ascending order"
    
    # Validate price categories
    assert len(PRICE_CATEGORIES) == 5, "Exactly 5 price categories required"
    
    # Validate price thresholds
    assert ABSOLUTE_CHEAP_LIMIT > 0, "Absolute cheap limit must be positive"
    assert DEFAULT_EXTREME_MULTIPLIER > 1.0, "Extreme multiplier should be greater than 1.0"
    assert MIN_SAMPLES_FOR_CLASSIFICATION > 0, "Minimum samples must be positive"
    
    # Validate multipliers are in logical order
    multipliers = [VERY_CHEAP_MULTIPLIER, CHEAP_MULTIPLIER, NORMAL_MULTIPLIER, EXPENSIVE_MULTIPLIER]
    assert multipliers == sorted(multipliers), "Price multipliers must be in ascending order"
    
    # Validate temperature ranges
    assert MIN_FAKE_TEMP < MAX_FAKE_TEMP, "Min fake temp must be less than max fake temp"
    assert HOLIDAY_TEMP > 0, "Holiday temperature must be positive"
    
    # Validate time settings
    assert DEFAULT_TRAILING_HOURS > 0, "Trailing hours must be positive"
    assert MIN_LEAD_TIME <= MAX_LEAD_TIME, "Min lead time must be <= max lead time"


# Run validation on import
validate_settings()
