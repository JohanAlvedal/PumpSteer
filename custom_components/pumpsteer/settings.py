# Temperaturinställningar
COMFORT_TEMP_TARGET = 21.0
SUMMER_TEMP_THRESHOLD = 17.5
HOLIDAY_TEMP = 16.0

# Elprisinställningar
HIGH_PRICE_THRESHOLD = 2.00  # kronor/kWh
LOW_PRICE_THRESHOLD = 0.80

# Tröghetsvärden (husets respons på tempförändringar)
DEFAULT_HOUSE_INERTIA = 3  # timmar
MAX_PREBOOST_HOURS = 6

# Datumformat för semester
DATE_FORMAT = "%Y-%m-%d"

# Pre_boost Inställningar

# Maximal pre-boostjustering i grader
MAX_PREBOOST_ADJUSTMENT = 5.0  # °C

# Minsta elpris som triggar pre-boost
PREBOOST_PRICE_THRESHOLD = 1.20  # SEK/kWh

# Minsta temperaturprognos som kräver pre-boost
PREBOOST_TEMP_THRESHOLD = 2.0  # °C

# Tröghetsmultiplikator för att skala pre-boostens tid
INERTIA_SCALING_FACTOR = 1.0  # kan justeras för att påverka hur långt i förväg pre-boost triggas
