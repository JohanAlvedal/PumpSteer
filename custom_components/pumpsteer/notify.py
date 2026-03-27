"""PumpSteer notifications — listens on the main sensor's mode attribute."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

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
        "Electricity is cheap — pre-heating now before prices rise.",
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


def _get_main_sensor_entity_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Resolve the entity_id of the main PumpSteer sensor for this config entry."""
    registry = er.async_get(hass)
    return registry.async_get_entity_id("sensor", DOMAIN, entry.entry_id)


@callback
def async_setup_notifications(hass: HomeAssistant, entry: ConfigEntry):
    """Call from __init__.py async_setup_entry. Returns unsubscribe callable."""

    main_entity_id = _get_main_sensor_entity_id(hass, entry)
    if not main_entity_id:
        # Entity not yet registered at setup time — fall back to slug-based ID.
        main_entity_id = "sensor.pumpsteer"

    _LOGGER.debug("PumpSteer notifications watching: %s", main_entity_id)

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

        title, message = MODE_NOTIFICATIONS[new_mode]
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
