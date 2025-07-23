# Default house inertia (used if input_number.house_inertia is not set)
DEFAULT_HOUSE_INERTIA = 1.0

# Holiday mode settings
HOLIDAY_TEMP = 16.0  # Target temperature when holiday mode is active

# Braking and output settings
BRAKING_MODE_TEMP = 22.5         # Virtual outdoor temperature when braking due to high price
PREBOOST_OUTPUT_TEMP = -15.0     # Virtual outdoor temperature when pre-boosting
NORMAL_MODE_MAX_OUTPUT_TEMP = 22.5 # Max virtual outdoor temp in normal operation
NORMAL_MODE_MIN_OUTPUT_TEMP = -10.0 # Min virtual outdoor temp in normal operation
AGGRESSIVENESS_SCALING_FACTOR = 0.5 # Factor for aggressiveness in normal mode
HIGH_PRICE_THRESHOLD = 1

# electricity_price.py
DEFAULT_PERCENTILES = [10, 30, 85, 95]
DEFAULT_EXTREME_MULTIPLIER = 1.5
MIN_SAMPLES_FOR_CLASSIFICATION = 5
PRICE_CATEGORIES = ["very_cheap", "cheap", "normal", "expensive", "very_expensive"]
ABSOLUTE_CHEAP_LIMIT = 0.50

# Pre-boost strategy settings (for pre_boost.py)
COLD_HOUR_TEMP_THRESHOLD = 10.0 # Max temperature for an hour to be considered "cold" for pre-boost strategy
INERTIA_LEAD_TIME_FACTOR = 0.75
MIN_PRICE_THRESHOLD_RATIO = 0.5
MAX_PRICE_THRESHOLD_RATIO = 0.9
PREBOOST_AGGRESSIVENESS_SCALING_FACTOR = 0.04
BASE_PRICE_THRESHOLD_RATIO = 0.9
MIN_LEAD_TIME = 0.5
MAX_LEAD_TIME = 3.0
PREBOOST_MAX_OUTDOOR_TEMP = 10.0  # Max outdoor temp for pre-boost to be considered
MAX_PREBOOST_HOURS = 6           # How many hours ahead to look for pre-boost
PREBOOST_TEMP_THRESHOLD = 2.0    # How many degrees colder than target to trigger pre-boost
PREBOOST_PRICE_THRESHOLD = 1.20  # SEK/kWh - Absolute price threshold for pre-boost

# temp_control_logic.py
MIN_FAKE_TEMP = -25.0
MAX_FAKE_TEMP = 30.0
BRAKE_FAKE_TEMP = 23.5

PUMPSTEER_INTEGRAL_GAIN = 0.05  # Justerbar, finjusteras i Home Assistant
