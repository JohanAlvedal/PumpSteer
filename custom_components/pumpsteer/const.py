"""Constants for PumpSteer."""

DOMAIN = "pumpsteer"
OHMIGO_RELAY_ENTITY = "ohmigo_relay_entity"

# Dashboard panel and savings estimate (optional, observational only).
SHOW_PANEL_OPTION = "show_panel"
SAVINGS_KWH_OPTION = "savings_kwh_per_c_hour"

# Price-notification preferences (optional; legacy defaults stay unchanged).
NOTIFICATION_LEVEL_OPTION = "notification_level"
NOTIFICATION_COOLDOWN_OPTION = "notification_cooldown_minutes"
NOTIFICATION_LEVEL_ALL = "all"
NOTIFICATION_LEVEL_BRAKING_ONLY = "braking_only"
NOTIFICATION_LEVEL_OFF = "off"
NOTIFICATION_LEVELS = frozenset(
    {NOTIFICATION_LEVEL_ALL, NOTIFICATION_LEVEL_BRAKING_ONLY, NOTIFICATION_LEVEL_OFF}
)
NOTIFICATION_COOLDOWN_CHOICES = (0, 30, 60, 120)
