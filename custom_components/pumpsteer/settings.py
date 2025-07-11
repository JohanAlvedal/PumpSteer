# -----------------------------------------------
# 📦 Grundinställningar och systemparametrar
# -----------------------------------------------

# Standardvärde för husets tröghet (om input_number.house_inertia saknas)
DEFAULT_HOUSE_INERTIA = 1.0


# -----------------------------------------------
# 🏖️ Semesterläge (Holiday Mode)
# -----------------------------------------------

# Måltemperatur när semesterläget är aktivt (t.ex. när man är bortrest)
HOLIDAY_TEMP = 16.0

# -----------------------------------------------
# 🚫 Bromsning & Utgångstemperaturer
# -----------------------------------------------

# Virtuell utomhustemperatur som används när uppvärmning ska stoppas pga högt elpris
BRAKING_MODE_TEMP = 20.0

# Virtuell utomhustemperatur som simuleras vid pre-boost (för att starta värme tidigare)
PREBOOST_OUTPUT_TEMP = -15.0

# Max och min temperaturgränser som får användas som "falsk" utetemperatur
NORMAL_MODE_MAX_OUTPUT_TEMP = 30.0
NORMAL_MODE_MIN_OUTPUT_TEMP = -10.0

# Globala säkerhetsgränser för beräknad utomhustemperatur
MIN_FAKE_TEMP = -25.0  # Aldrig kallare än detta (säkerhetsgräns)
MAX_FAKE_TEMP = 30.0   # Aldrig varmare än detta (säkerhetsgräns)

# -----------------------------------------------
# ⚡ Pre-Boost – logik för att starta värme i förväg
# -----------------------------------------------

# Maximal verklig utetemperatur för att preboost ska vara aktuell
PREBOOST_MAX_OUTDOOR_TEMP = 10.0

# Hur många timmar framåt i tiden man får titta vid pre-boost-analys
MAX_PREBOOST_HOURS = 6

# Temperaturtröskel: hur mycket kallare det måste bli för att utlösa pre-boost
PREBOOST_TEMP_THRESHOLD = 2.0

# Absolut elpriströskel (kr/kWh) för att pre-boost ska aktiveras
PREBOOST_PRICE_THRESHOLD = 1.20

# Temperaturgräns per timme för att en framtida timme ska räknas som "kall"
COLD_HOUR_TEMP_THRESHOLD = 18.0

# -----------------------------------------------
# 🔥 Aggressivitetslogik (påverkar hur systemet reagerar på temperaturdiff)
# -----------------------------------------------

# Skalningsfaktor: hur mycket påverkan aggressiveness har på uppvärmningslogiken
AGGRESSIVENESS_SCALING_FACTOR = 0.5

# Tröskel för när pris anses vara "högt" (kan användas för blockering)
HIGH_PRICE_THRESHOLD = 1.0

# Faktor för att räkna ut försprångstid (lead time) baserat på tröghet
INERTIA_LEAD_TIME_FACTOR = 0.75

# Prisgränser för pre-boost baserat på aggressiveness
MIN_PRICE_THRESHOLD_RATIO = 0.5  # Lägre gräns (mest känslig)
MAX_PRICE_THRESHOLD_RATIO = 0.9  # Övre gräns (mest defensiv)
BASE_PRICE_THRESHOLD_RATIO = 0.9  # Baslinje innan justering med aggressiveness

# Begränsningar för försprångstid (lead time)
MIN_LEAD_TIME = 0.5  # minsta timmar att förskjuta uppvärmning
MAX_LEAD_TIME = 3.0  # max antal timmar att gå i förväg


