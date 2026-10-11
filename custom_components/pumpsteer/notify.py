import logging
import math
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    NOTIFICATION_COOLDOWN_CHOICES,
    NOTIFICATION_COOLDOWN_OPTION,
    NOTIFICATION_LEVEL_ALL,
    NOTIFICATION_LEVEL_BRAKING_ONLY,
    NOTIFICATION_LEVEL_OFF,
    NOTIFICATION_LEVEL_OPTION,
    NOTIFICATION_LEVELS,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

# Map from mode value → (title, message).
# Notification fires when mode transitions *into* one of these values.
MODE_NOTIFICATIONS = {
    "braking": (
        "🔴 Price braking active",
        "Electricity is expensive — heating has been reduced.",
    ),
    "preheating": (
        "🔥 Pre-heating started",
        "Heating is being boosted ahead of an upcoming expensive period.",
    ),
}


def _notifications_enabled(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return True if the notifications switch is on (or missing — fail open)."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_notifications_enabled"
    )
    if not entity_id:
        return True  # switch not yet registered — allow notification
    state = hass.states.get(entity_id)
    if state is None:
        return True  # unknown state — allow notification
    return state.state == "on"


def _notification_level(entry: ConfigEntry) -> str:
    """Return the configured price-alert level, preserving legacy defaults."""
    cfg = {**entry.data, **entry.options}
    level = cfg.get(NOTIFICATION_LEVEL_OPTION, NOTIFICATION_LEVEL_ALL)
    return (
        level
        if isinstance(level, str) and level in NOTIFICATION_LEVELS
        else NOTIFICATION_LEVEL_ALL
    )


def _notification_cooldown_minutes(entry: ConfigEntry) -> int:
    """Validate the configured same-mode repeat interval (zero = no limit)."""
    cfg = {**entry.data, **entry.options}
    raw = cfg.get(NOTIFICATION_COOLDOWN_OPTION, 0)
    try:
        minutes = int(raw)
    except (TypeError, ValueError, OverflowError):
        return 0
    return minutes if minutes in NOTIFICATION_COOLDOWN_CHOICES else 0


def _get_main_sensor_entity_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Resolve the entity_id of the main PumpSteer sensor for this config entry."""
    registry = er.async_get(hass)
    return registry.async_get_entity_id("sensor", DOMAIN, entry.entry_id)


def _notification_content(mode: str, state) -> tuple[str, str]:
    """Build notification content from the state that triggered the transition."""
    title, message = MODE_NOTIFICATIONS[mode]

    raw_price = state.attributes.get("current_price")
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return title, message

    if not math.isfinite(price):
        return title, message

    unit = state.attributes.get("current_price_unit")
    unit_suffix = f" {unit.strip()}" if isinstance(unit, str) and unit.strip() else ""
    return title, f"{message}\nCurrent price: {price:.2f}{unit_suffix}"


@callback
def async_setup_notifications(hass: HomeAssistant, entry: ConfigEntry):
    """Call from __init__.py async_setup_entry. Returns unsubscribe callable."""

    main_entity_id = _get_main_sensor_entity_id(hass, entry)
    if not main_entity_id:
        # Entity not yet registered at setup time — fall back to slug-based ID.
        main_entity_id = "sensor.pumpsteer"

    _LOGGER.debug("PumpSteer notifications watching: %s", main_entity_id)
    last_sent_by_mode: dict[str, float] = {}

    @callback
    def _on_state_change(event):
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if new_state is None:
            return

        old_mode = old_state.attributes.get("mode") if old_state else None
        new_mode = new_state.attributes.get("mode")

        if new_mode == old_mode:
            return  # mode unchanged — nothing to notify

        if new_mode not in MODE_NOTIFICATIONS:
            return  # entering a non-notifiable mode

        if not _notifications_enabled(hass, entry):
            _LOGGER.debug(
                "PumpSteer notifications disabled — skipping mode=%s", new_mode
            )
            return

        level = _notification_level(entry)
        if level == NOTIFICATION_LEVEL_OFF or (
            level == NOTIFICATION_LEVEL_BRAKING_ONLY and new_mode != "braking"
        ):
            _LOGGER.debug(
                "PumpSteer price notification filtered: mode=%s level=%s",
                new_mode,
                level,
            )
            return

        # A preheating notification must not silence the first braking alert.
        # Monotonic time survives DST changes, while counters intentionally
        # reset after an integration reload or a Home Assistant restart.
        now = monotonic()
        cooldown_seconds = _notification_cooldown_minutes(entry) * 60
        last_sent = last_sent_by_mode.get(new_mode)
        if (
            cooldown_seconds > 0
            and last_sent is not None
            and now - last_sent < cooldown_seconds
        ):
            _LOGGER.debug(
                "PumpSteer notification in cooldown: mode=%s remaining=%.0fs",
                new_mode,
                cooldown_seconds - (now - last_sent),
            )
            return

        title, message = _notification_content(new_mode, new_state)
        last_sent_by_mode[new_mode] = now
        hass.async_create_task(
            async_send_notification(hass, entry, title, message, "pumpsteer_price")
        )

    unsub = async_track_state_change_event(hass, [main_entity_id], _on_state_change)
    return unsub


async def async_send_notification(
    hass: HomeAssistant,
    entry: ConfigEntry,
    title: str,
    message: str,
    notification_id: str = "pumpsteer",
) -> None:
    """Send via notify_service (from options), or fall back to persistent_notification."""
    service = {**entry.data, **entry.options}.get("notify_service", "")

    if service:
        domain, svc = service.split(".", 1) if "." in service else ("notify", service)
        try:
            await hass.services.async_call(
                domain, svc, {"title": title, "message": message}
            )
            return
        except Exception as err:
            _LOGGER.warning(
                "PumpSteer notify failed (%s), using persistent_notification: %s",
                service,
                err,
            )

    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": title, "message": message, "notification_id": notification_id},
    )
