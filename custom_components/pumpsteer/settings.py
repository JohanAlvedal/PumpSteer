from typing import List, Final
import logging

_LOGGER = logging.getLogger(__name__)

# === VERSIONSINFO ===
PUMPSTEER_VERSION: Final[str] = "1.2.1"

# === HOUSE CONTROL SETTINGS ===
DEFAULT_HOUSE_INERTIA: Final[float] = 1.0  # Default house thermal inertia

# === HOLIDAY MODE SETTINGS ===
HOLIDAY_TEMP: Final[float] = 16.0          # °C - Target temperature when holiday mode is active

# === TEMPERATURE CONTROL SETTINGS ===
BRAKING_MODE_TEMP: Final[float] = 25.0         # °C - Virtual outdoor temperature when braking due to high price
PREBOOST_OUTPUT_TEMP: Final[float] = -15.0     # °C - Virtual outdoor temperature when pre-boosting
AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.5  # Factor for aggressiveness in normal mode
PREBOOST_MAX_OUTDOOR_TEMP: Final[float] = 10.0  # °C - Max outdoor temp for pre-boost to be considered

# === TEMPERATURE CONTROL LOGIC ===
MIN_FAKE_TEMP: Final[float] = -25.0
MAX_FAKE_TEMP: Final[float] = 30.0
BRAKE_FAKE_TEMP: Final[float] = 25.0

# === ELECTRICITY PRICE CLASSIFICATION ===
DEFAULT_PERCENTILES: Final[List[int]] = [10, 30, 85, 95]  # Percentiles for 5-category classification
DEFAULT_EXTREME_MULTIPLIER: Final[float] = 1.5             # Multiplier for extreme price detection
MIN_SAMPLES_FOR_CLASSIFICATION: Final[int] = 5            # Minimum number of price samples needed
PRICE_CATEGORIES: Final[List[str]] = [                     # Price categories in ascending order
    "very_cheap", "cheap", "normal", "expensive", "very_expensive"
]
ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.60                 # SEK/kWh - Absolute threshold for cheap prices
DEFAULT_TRAILING_HOURS: Final[int] = 72                   # Hours of historical data to consider
MAX_PRICE_WARNING_THRESHOLD: Final[float] = 3.0           # SEK/kWh - Log warning for extremely high prices

# === HYBRID CLASSIFICATION THRESHOLDS ===
VERY_CHEAP_MULTIPLIER: Final[float] = 0.60    # 60% of average price
CHEAP_MULTIPLIER: Final[float] = 0.90         # 90% of average price  
NORMAL_MULTIPLIER: Final[float] = 1.40        # 140% of average price
EXPENSIVE_MULTIPLIER: Final[float] = 1.60     # 160% of average price

# === PRE-BOOST STRATEGY SETTINGS ===
MIN_PRICE_THRESHOLD_RATIO: Final[float] = 0.5
MAX_PRICE_THRESHOLD_RATIO: Final[float] = 0.9
PREBOOST_AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.04
BASE_PRICE_THRESHOLD_RATIO: Final[float] = 0.9
MAX_PREBOOST_HOURS: Final[int] = 6             # How many hours ahead to look for pre-boost
PREBOOST_TEMP_THRESHOLD: Final[float] = 2.0    # °C - How many degrees colder than target to trigger pre-boost

# === FÖRBÄTTRADE PRE-BOOST TIMING KONSTANTER ===
PREBOOST_MIN_ADVANCE_FACTOR: Final[float] = 0.5   # Min advance = inertia * 0.5
PREBOOST_MAX_ADVANCE_FACTOR: Final[float] = 1.2   # Max advance = inertia * 1.2
PREBOOST_MIN_ADVANCE_HOURS: Final[float] = 1.0    # Absolut minimum förhandstid
PREBOOST_MAX_ADVANCE_HOURS: Final[float] = 3.0    # Absolut maximum förhandstid
SEVERITY_ADJUSTMENT_FACTOR: Final[float] = 0.3    # Hur mycket severity påverkar timing

# === NYA PRE-BOOST KRAV ===
PREBOOST_REQUIRE_VERY_CHEAP_NOW: Final[bool] = True     # Aktivera krav på mycket billigt just nu
PREBOOST_MIN_DURATION_HOURS: Final[int] = 2             # Minsta peak-längd som krävs för att trigga preboost
PREBOOST_CHEAP_NOW_MULTIPLIER: Final[float] = 0.6       # T.ex. 60% av maxpris = "väldigt billigt"

# === VALIDERINGS-KONSTANTER ===
MIN_REASONABLE_TEMP: Final[float] = -50.0      # °C - Minimum rimlig temperatur
MAX_REASONABLE_TEMP: Final[float] = 50.0       # °C - Maximum rimlig temperatur
MIN_REASONABLE_PRICE: Final[float] = -2.0      # SEK/kWh - Minimum rimligt elpris (negativa priser förekommer)
MAX_REASONABLE_PRICE: Final[float] = 15.0      # SEK/kWh - Maximum rimligt elpris

# Grundläggande validering av inställningar
def validate_core_settings() -> None:
    """Validera grundläggande inställningar."""
    errors = []
    
    # Validera percentiler
    if len(DEFAULT_PERCENTILES) != 4:
        errors.append("Exactly 4 percentiles required for 5-category classification")
    
    if not all(0 <= p <= 100 for p in DEFAULT_PERCENTILES):
        errors.append("Percentiles must be between 0 and 100")
    
    if DEFAULT_PERCENTILES != sorted(DEFAULT_PERCENTILES):
        errors.append("Percentiles must be in ascending order")
    
    # Validera priskategorier
    if len(PRICE_CATEGORIES) != 5:
        errors.append("Exactly 5 price categories required")
    
    # Validera temperaturintervall
    if MIN_FAKE_TEMP >= MAX_FAKE_TEMP:
        errors.append("Min fake temp must be less than max fake temp")
    
    # Validera multiplikatorer är i logisk ordning
    multipliers = [VERY_CHEAP_MULTIPLIER, CHEAP_MULTIPLIER, NORMAL_MULTIPLIER, EXPENSIVE_MULTIPLIER]
    if multipliers != sorted(multipliers):
        errors.append("Price multipliers must be in ascending order")
    
    # Validera pre-boost timing konstanter
    if PREBOOST_MIN_ADVANCE_FACTOR >= PREBOOST_MAX_ADVANCE_FACTOR:
        errors.append("Min advance factor must be less than max advance factor")
    
    if PREBOOST_MIN_ADVANCE_HOURS >= PREBOOST_MAX_ADVANCE_HOURS:
        errors.append("Min advance hours must be less than max advance hours")
    
    # Validera rimliga värden
    if MIN_REASONABLE_TEMP >= MAX_REASONABLE_TEMP:
        errors.append("Min reasonable temp must be less than max reasonable temp")
    
    if MIN_REASONABLE_PRICE >= MAX_REASONABLE_PRICE:
        errors.append("Min reasonable price must be less than max reasonable price")
    
    if errors:
        error_msg = f"Settings validation failed: {'; '.join(errors)}"
        _LOGGER.error(error_msg)
        raise ValueError(error_msg)

# Kör validering vid import
try:
    validate_core_settings()
    _LOGGER.debug(f"PumpSteer core settings loaded successfully (version {PUMPSTEER_VERSION})")
except Exception as e:
    _LOGGER.error(f"Failed to load PumpSteer settings: {e}")
    raise
