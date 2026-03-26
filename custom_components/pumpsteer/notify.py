"""PumpSteer notifications — listens on is_braking and is_preboosting."""

import logging
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

WATCHED = {
    "sensor.pumpsteer_is_braking": (
        "🔴 Price braking active",
        "Electricity is expensive — heating has been reduced.",
    ),
    "sensor.pumpsteer_is_preboosting": (
        "🔥 Pre-heating started",
        "Electricity is cheap — pre-heating now before prices rise.",
    ),
}


@callback
def async_setup_notifications(hass: HomeAssistant, entry: ConfigEntry):
    """Call from __init__.py async_setup_entry. Returns unsubscribe callable."""

    @callback
    def _on_change(event):
        old = getattr(event.data.get("old_state"), "state", None)
        new = getattr(event.data.get("new_state"), "state", None)
        entity_id = event.data.get("entity_id")

        if new != "True" or old == "True":
            return  # only fire on False → True

        title, message = WATCHED[entity_id]
        hass.async_create_task(_send(hass, entry, title, message))

    unsubs = [
        async_track_state_change_event(hass, [eid], _on_change) for eid in WATCHED
    ]

    return lambda: [u() for u in unsubs]


async def _send(hass: HomeAssistant, entry: ConfigEntry, title: str, message: str):
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
        {"title": title, "message": message, "notification_id": "pumpsteer_price"},
    )
