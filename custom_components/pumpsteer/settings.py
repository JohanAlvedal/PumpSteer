# Default house inertia (used if input_number.house_inertia is not set)
DEFAULT_HOUSE_INERTIA = 1.0

# Holiday mode settings
HOLIDAY_TEMP = 16.0  # Target temperature when holiday mode is active

# Pre-boost settings
PREBOOST_MAX_OUTDOOR_TEMP = 10.0  # Max outdoor temp for pre-boost to be considered
MAX_PREBOOST_HOURS = 6           # How many hours ahead to look for pre-boost
PREBOOST_TEMP_THRESHOLD = 2.0    # How many degrees colder than target to trigger pre-boost
PREBOOST_PRICE_THRESHOLD = 1.20  # SEK/kWh - Absolute price threshold for pre-boost

# Braking and output settings
BRAKING_MODE_TEMP = 20.0         # Virtual outdoor temperature when braking due to high price
PREBOOST_OUTPUT_TEMP = -15.0     # Virtual outdoor temperature when pre-boosting

NORMAL_MODE_MAX_OUTPUT_TEMP = 20.0 # Max virtual outdoor temp in normal operation
NORMAL_MODE_MIN_OUTPUT_TEMP = -10.0 # Min virtual outdoor temp in normal operation

AGGRESSIVENESS_SCALING_FACTOR = 0.5 # Factor for aggressiveness in normal mode

# Pre-boost strategy settings (for pre_boost.py)
COLD_HOUR_TEMP_THRESHOLD = 18.0 # Max temperature for an hour to be considered "cold" for pre-boost strategy
