from typing import List, Final, Dict, Any
import logging

_LOGGER = logging.getLogger(__name__)

# === VERSIONSINFO ===
PUMPSTEER_VERSION: Final[str] = "1.2.1"

# === HOUSE CONTROL SETTINGS ===
DEFAULT_HOUSE_INERTIA: Final[float] = 1.0  # Default house thermal inertia
MIN_HOUSE_INERTIA: Final[float] = 0.1      # Minimum inertia value
MAX_HOUSE_INERTIA: Final[float] = 10.0     # Maximum inertia value

# === HOLIDAY MODE SETTINGS ===
HOLIDAY_TEMP: Final[float] = 16.0          # °C - Target temperature when holiday mode is active
MIN_HOLIDAY_TEMP: Final[float] = 10.0      # °C - Minimum allowed holiday temperature
MAX_HOLIDAY_TEMP: Final[float] = 20.0      # °C - Maximum allowed holiday temperature

# === TEMPERATURE CONTROL SETTINGS ===
BRAKING_MODE_TEMP: Final[float] = 22.5         # °C - Virtual outdoor temperature when braking due to high price
PREBOOST_OUTPUT_TEMP: Final[float] = -15.0     # °C - Virtual outdoor temperature when pre-boosting
NORMAL_MODE_MAX_OUTPUT_TEMP: Final[float] = 22.5  # °C - Max virtual outdoor temp in normal operation
NORMAL_MODE_MIN_OUTPUT_TEMP: Final[float] = -10.0  # °C - Min virtual outdoor temp in normal operation
AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.5  # Factor for aggressiveness in normal mode

# Säkerhetsgränser för temperaturer
MIN_SAFE_TEMP: Final[float] = -30.0        # °C - Absolute minimum safe temperature
MAX_SAFE_TEMP: Final[float] = 40.0         # °C - Absolute maximum safe temperature
TEMP_DIFF_THRESHOLD: Final[float] = 0.5    # °C - Threshold for neutral zone

# === AGGRESSIVENESS SETTINGS ===
MIN_AGGRESSIVENESS: Final[float] = 0.0     # Minimum aggressiveness value
MAX_AGGRESSIVENESS: Final[float] = 5.0     # Maximum aggressiveness value
DEFAULT_AGGRESSIVENESS: Final[float] = 0.0 # Default aggressiveness

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

# Prisvalidering
MIN_REASONABLE_PRICE: Final[float] = -2.0  # SEK/kWh - Negativa priser kan förekomma
MAX_REASONABLE_PRICE: Final[float] = 15.0  # SEK/kWh - Maximal rimlig elpris

# === HYBRID CLASSIFICATION THRESHOLDS ===
VERY_CHEAP_MULTIPLIER: Final[float] = 0.60    # 60% of average price
CHEAP_MULTIPLIER: Final[float] = 0.90         # 90% of average price  
NORMAL_MULTIPLIER: Final[float] = 1.15        # 115% of average price
EXPENSIVE_MULTIPLIER: Final[float] = 1.40     # 140% of average price

# === LEGACY PRICE THRESHOLD ===
HIGH_PRICE_THRESHOLD: Final[float] = 1.0       # SEK/kWh - Legacy threshold for temperature control

# === PRE-BOOST STRATEGY SETTINGS ===
COLD_HOUR_TEMP_THRESHOLD: Final[float] = 10.0  # °C - Max temperature for an hour to be considered "cold"
INERTIA_LEAD_TIME_FACTOR: Final[float] = 0.75  # Legacy lead time calculation (för bakåtkompatibilitet)
MIN_PRICE_THRESHOLD_RATIO: Final[float] = 0.5
MAX_PRICE_THRESHOLD_RATIO: Final[float] = 0.9
PREBOOST_AGGRESSIVENESS_SCALING_FACTOR: Final[float] = 0.04
BASE_PRICE_THRESHOLD_RATIO: Final[float] = 0.9
MIN_LEAD_TIME: Final[float] = 0.5              # Hours (legacy)
MAX_LEAD_TIME: Final[float] = 3.0              # Hours (legacy)
PREBOOST_MAX_OUTDOOR_TEMP: Final[float] = 10.0  # °C - Max outdoor temp for pre-boost to be considered
MAX_PREBOOST_HOURS: Final[int] = 6             # How many hours ahead to look for pre-boost
PREBOOST_TEMP_THRESHOLD: Final[float] = 2.0    # °C - How many degrees colder than target to trigger pre-boost
PREBOOST_PRICE_THRESHOLD: Final[float] = 1.20  # SEK/kWh - Absolute price threshold for pre-boost

# === FÖRBÄTTRADE PRE-BOOST TIMING KONSTANTER ===
PREBOOST_MIN_ADVANCE_FACTOR: Final[float] = 0.5   # Min advance = inertia * 0.5
PREBOOST_MAX_ADVANCE_FACTOR: Final[float] = 1.2   # Max advance = inertia * 1.2
PREBOOST_MIN_ADVANCE_HOURS: Final[float] = 1.0    # Absolut minimum förhandstid
PREBOOST_MAX_ADVANCE_HOURS: Final[float] = 3.0    # Absolut maximum förhandstid
SEVERITY_ADJUSTMENT_FACTOR: Final[float] = 0.3    # Hur mycket severity påverkar timing

# === VALIDERINGS-KONSTANTER ===
MIN_REASONABLE_TEMP: Final[float] = -50.0      # °C - Minimum rimlig temperatur
MAX_REASONABLE_TEMP: Final[float] = 50.0       # °C - Maximum rimlig temperatur
MIN_REASONABLE_PRICE: Final[float] = -2.0      # SEK/kWh - Minimum rimligt elpris (negativa priser förekommer)
MAX_REASONABLE_PRICE: Final[float] = 15.0      # SEK/kWh - Maximum rimligt elpris

# === TEMPERATURE CONTROL LOGIC ===
MIN_FAKE_TEMP: Final[float] = -25.0
MAX_FAKE_TEMP: Final[float] = 30.0
BRAKE_FAKE_TEMP: Final[float] = 25.0
PUMPSTEER_INTEGRAL_GAIN: Final[float] = 0.05   # Adjustable, fine-tuned in Home Assistant

# === SYSTEM LIMITS ===
MAX_UPDATE_FREQUENCY: Final[int] = 60         # Seconds - Minimum time between updates
MAX_LOG_ENTRIES: Final[int] = 100             # Maximum number of log entries to keep
MAX_FORECAST_HOURS: Final[int] = 48           # Maximum hours of forecast data to process

# === VALIDATION RANGES ===
TEMP_VALIDATION_RANGES: Final[Dict[str, tuple]] = {
    "indoor": (-10.0, 35.0),      # Rimliga inomhustemperaturer
    "outdoor": (-40.0, 50.0),     # Rimliga utomhustemperaturer  
    "target": (5.0, 30.0),        # Rimliga måltemperaturer
    "summer_threshold": (10.0, 25.0)  # Rimliga sommartrösklar
}

PRICE_VALIDATION_RANGES: Final[Dict[str, tuple]] = {
    "normal": (-2.0, 15.0),       # Normal prisrange
    "warning": (5.0, 15.0),       # Varningsnivå för höga priser
    "extreme": (10.0, 50.0)       # Extrema priser
}

# === DEFAULT ENTITY NAMES ===
DEFAULT_ENTITY_NAMES: Final[Dict[str, str]] = {
    "aggressiveness": "input_number.pumpsteer_aggressiveness",
    "house_inertia": "input_number.house_inertia", 
    "price_model": "input_select.pumpsteer_price_model",
    "holiday_mode": "input_boolean.pumpsteer_holiday_mode",
    "holiday_start": "input_datetime.pumpsteer_holiday_start",
    "holiday_end": "input_datetime.pumpsteer_holiday_end"
}

# === PRICE CLASSIFICATION MODES ===
PRICE_CLASSIFICATION_MODES: Final[List[str]] = ["hybrid", "percentiles"]
DEFAULT_PRICE_MODE: Final[str] = "hybrid"

# === ERROR HANDLING SETTINGS ===
MAX_CONSECUTIVE_ERRORS: Final[int] = 5        # Max errors before failsafe mode
ERROR_RESET_TIME: Final[int] = 300            # Seconds before error counter resets
FAILSAFE_MODE_TEMP: Final[float] = 20.0       # °C - Temperature in failsafe mode


def validate_settings() -> None:
    """Validera att alla inställningar är konsekventa och rimliga."""
    errors = []
    warnings = []
    
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
    
    # Validera priströsklar
    if ABSOLUTE_CHEAP_LIMIT <= 0:
        errors.append("Absolute cheap limit must be positive")
    
    if DEFAULT_EXTREME_MULTIPLIER <= 1.0:
        warnings.append("Extreme multiplier should be greater than 1.0")
    
    if MIN_SAMPLES_FOR_CLASSIFICATION <= 0:
        errors.append("Minimum samples must be positive")
    
    # Validera multiplikatorer är i logisk ordning
    multipliers = [VERY_CHEAP_MULTIPLIER, CHEAP_MULTIPLIER, NORMAL_MULTIPLIER, EXPENSIVE_MULTIPLIER]
    if multipliers != sorted(multipliers):
        errors.append("Price multipliers must be in ascending order")
    
    # Validera temperaturintervall
    if MIN_FAKE_TEMP >= MAX_FAKE_TEMP:
        errors.append("Min fake temp must be less than max fake temp")
    
    if HOLIDAY_TEMP <= 0:
        errors.append("Holiday temperature must be positive")
    
    if not (MIN_HOLIDAY_TEMP <= HOLIDAY_TEMP <= MAX_HOLIDAY_TEMP):
        warnings.append(f"Holiday temp {HOLIDAY_TEMP} outside recommended range {MIN_HOLIDAY_TEMP}-{MAX_HOLIDAY_TEMP}")
    
    # Validera tidsinställningar
    if DEFAULT_TRAILING_HOURS <= 0:
        errors.append("Trailing hours must be positive")
    
    if MIN_LEAD_TIME > MAX_LEAD_TIME:
        errors.append("Min lead time must be <= max lead time")
    
    # Validera aggressiveness-intervall
    if not (MIN_AGGRESSIVENESS <= DEFAULT_AGGRESSIVENESS <= MAX_AGGRESSIVENESS):
        errors.append(f"Default aggressiveness {DEFAULT_AGGRESSIVENESS} outside valid range {MIN_AGGRESSIVENESS}-{MAX_AGGRESSIVENESS}")
    
    # Validera pre-boost inställningar
    if MAX_PREBOOST_HOURS <= 0:
        errors.append("Max preboost hours must be positive")
    
    if PREBOOST_TEMP_THRESHOLD <= 0:
        warnings.append("Preboost temperature threshold should be positive")
    
    # Validera nya pre-boost timing konstanter
    if PREBOOST_MIN_ADVANCE_FACTOR >= PREBOOST_MAX_ADVANCE_FACTOR:
        errors.append("Min advance factor must be less than max advance factor")
    
    if PREBOOST_MIN_ADVANCE_HOURS >= PREBOOST_MAX_ADVANCE_HOURS:
        errors.append("Min advance hours must be less than max advance hours")
    
    if not (0.0 <= SEVERITY_ADJUSTMENT_FACTOR <= 1.0):
        warnings.append(f"Severity adjustment factor {SEVERITY_ADJUSTMENT_FACTOR} should be between 0.0-1.0")
    
    # Validera temperatur- och prisvalidering
    if MIN_REASONABLE_TEMP >= MAX_REASONABLE_TEMP:
        errors.append("Min reasonable temp must be less than max reasonable temp")
    
    if MIN_REASONABLE_PRICE >= MAX_REASONABLE_PRICE:
        errors.append("Min reasonable price must be less than max reasonable price")
    
    # Validera prisintervall
    if MIN_REASONABLE_PRICE >= MAX_REASONABLE_PRICE:
        errors.append("Min reasonable price must be less than max reasonable price")
    
    # Logga resultat
    if errors:
        error_msg = f"Settings validation failed: {'; '.join(errors)}"
        _LOGGER.error(error_msg)
        raise ValueError(error_msg)
    
    if warnings:
        warning_msg = f"Settings validation warnings: {'; '.join(warnings)}"
        _LOGGER.warning(warning_msg)
    
    _LOGGER.debug("Settings validation completed successfully")


def get_setting_info() -> Dict[str, Any]:
    """Hämta information om aktuella inställningar för debugging."""
    return {
        "version": PUMPSTEER_VERSION,
        "temperature_limits": {
            "min_fake": MIN_FAKE_TEMP,
            "max_fake": MAX_FAKE_TEMP,
            "holiday": HOLIDAY_TEMP,
            "braking": BRAKING_MODE_TEMP,
            "preboost": PREBOOST_OUTPUT_TEMP
        },
        "price_settings": {
            "categories": PRICE_CATEGORIES,
            "percentiles": DEFAULT_PERCENTILES,
            "trailing_hours": DEFAULT_TRAILING_HOURS,
            "classification_modes": PRICE_CLASSIFICATION_MODES
        },
        "preboost_settings": {
            "max_hours": MAX_PREBOOST_HOURS,
            "temp_threshold": PREBOOST_TEMP_THRESHOLD,
            "max_outdoor_temp": PREBOOST_MAX_OUTDOOR_TEMP,
            "lead_time_range": (MIN_LEAD_TIME, MAX_LEAD_TIME)
        },
        "validation_ranges": {
            "temperature": TEMP_VALIDATION_RANGES,
            "price": PRICE_VALIDATION_RANGES
        },
        "system_limits": {
            "max_update_frequency": MAX_UPDATE_FREQUENCY,
            "max_forecast_hours": MAX_FORECAST_HOURS,
            "max_consecutive_errors": MAX_CONSECUTIVE_ERRORS
        }
    }


def validate_temperature_value(temp: float, temp_type: str = "general") -> bool:
    """
    Validera ett temperaturvärde mot definierade gränser.
    
    Args:
        temp: Temperaturvärde att validera
        temp_type: Typ av temperatur ("indoor", "outdoor", "target", "summer_threshold")
        
    Returns:
        True om temperaturen är giltig
    """
    if temp_type in TEMP_VALIDATION_RANGES:
        min_temp, max_temp = TEMP_VALIDATION_RANGES[temp_type]
        return min_temp <= temp <= max_temp
    else:
        # Generell validering
        return MIN_SAFE_TEMP <= temp <= MAX_SAFE_TEMP


def validate_price_value(price: float, price_type: str = "normal") -> bool:
    """
    Validera ett prisvärde mot definierade gränser.
    
    Args:
        price: Prisvärde att validera
        price_type: Typ av prisvalidering ("normal", "warning", "extreme")
        
    Returns:
        True om priset är giltigt
    """
    if price_type in PRICE_VALIDATION_RANGES:
        min_price, max_price = PRICE_VALIDATION_RANGES[price_type]
        return min_price <= price <= max_price
    else:
        # Generell validering
        return MIN_REASONABLE_PRICE <= price <= MAX_REASONABLE_PRICE


def get_safe_value(value: float, min_val: float, max_val: float, default: float) -> float:
    """
    Säkerställ att ett värde är inom giltigt intervall.
    
    Args:
        value: Värde att kontrollera
        min_val: Minimivärde
        max_val: Maximivärde
        default: Standardvärde om värdet är utanför intervallet
        
    Returns:
        Säkert värde inom intervallet
    """
    if min_val <= value <= max_val:
        return value
    else:
        _LOGGER.warning(f"Value {value} outside range [{min_val}, {max_val}], using default {default}")
        return default


# Kör validering vid import
try:
    validate_settings()
    _LOGGER.debug(f"PumpSteer settings loaded successfully (version {PUMPSTEER_VERSION})")
except Exception as e:
    _LOGGER.error(f"Failed to load PumpSteer settings: {e}")
    raise
