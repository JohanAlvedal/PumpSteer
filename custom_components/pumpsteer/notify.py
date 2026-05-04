import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

MODE_TITLES = {
    "pre_braking": "🟠 Price brake preparing",
    "braking": "🔴 Price braking active",
    "preheating": "🔥 Pre-heating started",
    "normal": "✅ Normal operation",
    "holiday": "🏖️ Holiday operation",
    "summer_mode": "☀️ Summer mode",
    "safe_mode": "⚠️ Safe mode",
    "precool": "🌡️ Precooling active",
    "error": "❌ PumpSteer error",
}


def _notifications_enabled(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return True if the notifications switch is on (or missing — fail open)."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "switch",
        DOMAIN,
        f"{entry.entry_id}_notifications_enabled",
    )
    if not entity_id:
        return True
    state = hass.states.get(entity_id)
    if state is None:
        return True
    return state.state == "on"


def _get_main_sensor_entity_id(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> str | None:
    """Resolve the entity_id of the main PumpSteer sensor for this config entry."""
    registry = er.async_get(hass)
    return registry.async_get_entity_id("sensor", DOMAIN, entry.entry_id)


def _cfg(entry: ConfigEntry) -> dict[str, Any]:
    """Return merged config entry data and options."""
    return {**entry.data, **entry.options}


def _debug_notifications_enabled(entry: ConfigEntry) -> bool:
    """Return True if debug notifications are enabled in options."""
    return bool(_cfg(entry).get("debug_notifications", False))


def _is_brake_mode(mode: str | None) -> bool:
    """Return True if the mode represents active or ramping brake behavior."""
    return mode in {"pre_braking", "braking"}


def _build_mode_message(
    old_mode: str | None,
    new_mode: str | None,
    old_state,
    new_state,
) -> str:
    """Build a descriptive notification message for a mode transition."""
    attrs = new_state.attributes if new_state is not None else {}

    indoor = attrs.get("indoor_temperature")
    outdoor = attrs.get("outdoor_temperature")
    target = attrs.get("target_temperature")
    price_category = attrs.get("price_category")
    brake_factor = attrs.get("brake_factor")
    minutes_until_expensive = attrs.get("minutes_until_expensive")
    comfort_floor = attrs.get("comfort_floor_c")
    preheat_boost = attrs.get("preheat_boost_c")

    lines: list[str] = []

    if old_mode and new_mode:
        lines.append(f"Mode changed: {old_mode} → {new_mode}")
    elif new_mode:
        lines.append(f"Mode changed to: {new_mode}")
    else:
        lines.append("PumpSteer mode changed")

    if new_mode == "pre_braking":
        extra = "Brake ramp has started before an expensive period."
        if minutes_until_expensive is not None:
            extra += f" Expensive period starts in about {minutes_until_expensive} min."
        lines.append(extra)

    elif new_mode == "braking":
        extra = "Electricity is expensive — heating has been reduced."
        if brake_factor is not None:
            extra += f" Brake factor: {brake_factor}."
        lines.append(extra)

    elif _is_brake_mode(old_mode) and new_mode in {
        "normal",
        "holiday",
        "summer_mode",
        "safe_mode",
        "preheating",
        "precool",
    }:
        lines.append("Price braking has been released.")

    elif new_mode == "preheating":
        extra = "Electricity is favorable — pre-heating before higher prices."
        if preheat_boost is not None:
            extra += f" Boost: {preheat_boost} °C."
        lines.append(extra)

    elif new_mode == "safe_mode":
        status = attrs.get("status")
        if status:
            lines.append(str(status))

    elif new_mode == "summer_mode":
        lines.append(
            "Outdoor temperature is high enough — PumpSteer is passing through real outdoor temperature."
        )

    elif new_mode == "holiday":
        lines.append("Holiday mode target temperature is active.")

    elif new_mode == "precool":
        lines.append(
            "A warm period is expected — PumpSteer is reducing heating in advance."
        )

    if indoor is not None or target is not None or outdoor is not None:
        climate_parts: list[str] = []
        if indoor is not None:
            climate_parts.append(f"Indoor: {indoor} °C")
        if target is not None:
            climate_parts.append(f"Target: {target} °C")
        if outdoor is not None:
            climate_parts.append(f"Outdoor: {outdoor} °C")
        lines.append(" | ".join(climate_parts))

    if price_category is not None:
        price_line = f"Price category: {price_category}"
        if comfort_floor is not None:
            price_line += f" | Comfort floor: {comfort_floor} °C"
        lines.append(price_line)

    return "\n".join(lines)


def _should_notify_mode_change(
    entry: ConfigEntry,
    old_mode: str | None,
    new_mode: str | None,
) -> bool:
    """Decide whether this mode transition should trigger a notification."""
    if new_mode is None or new_mode == old_mode:
        return False

    if _debug_notifications_enabled(entry):
        return True

    # Important operational notifications even outside debug mode.
    if new_mode in {"pre_braking", "braking", "preheating", "safe_mode", "error"}:
        return True

    # Notify when brake is released.
    if _is_brake_mode(old_mode) and not _is_brake_mode(new_mode):
        return True

    return False


def _title_for_transition(old_mode: str | None, new_mode: str | None) -> str:
    """Return a suitable notification title."""
    if _is_brake_mode(old_mode) and new_mode in {"normal", "holiday", "summer_mode"}:
        return "🟢 Price braking released"

    if _is_brake_mode(old_mode) and new_mode == "safe_mode":
        return "⚠️ Price braking released"

    if new_mode in MODE_TITLES:
        return MODE_TITLES[new_mode]

    return "PumpSteer mode changed"


@callback
def async_setup_notifications(hass: HomeAssistant, entry: ConfigEntry):
    """Set up PumpSteer notifications and return unsubscribe callable."""
    main_entity_id = _get_main_sensor_entity_id(hass, entry)
    if not main_entity_id:
        main_entity_id = "sensor.pumpsteer"

    _LOGGER.debug("PumpSteer notifications watching: %s", main_entity_id)

    @callback
    def _on_state_change(event) -> None:
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if new_state is None:
            return

        old_mode = old_state.attributes.get("mode") if old_state else None
        new_mode = new_state.attributes.get("mode")

        if not _should_notify_mode_change(entry, old_mode, new_mode):
            _LOGGER.debug(
                "PumpSteer mode change ignored: %s -> %s",
                old_mode,
                new_mode,
            )
            return

        if not _notifications_enabled(hass, entry):
            _LOGGER.debug(
                "PumpSteer notifications disabled — skipping mode change %s -> %s",
                old_mode,
                new_mode,
            )
            return

        title = _title_for_transition(old_mode, new_mode)
        message = _build_mode_message(old_mode, new_mode, old_state, new_state)

        _LOGGER.debug(
            "PumpSteer sending notification for mode change: %s -> %s",
            old_mode,
            new_mode,
        )

        hass.async_create_task(
            async_send_notification(
                hass,
                entry,
                title,
                message,
                notification_id=f"pumpsteer_mode_{entry.entry_id}",
            )
        )

    return async_track_state_change_event(hass, [main_entity_id], _on_state_change)


async def async_send_notification(
    hass: HomeAssistant,
    entry: ConfigEntry,
    title: str,
    message: str,
    notification_id: str = "pumpsteer",
) -> None:
    """Send via notify service from options, or fall back to persistent notification."""
    service = _cfg(entry).get("notify_service", "")

    if service:
        domain, svc = service.split(".", 1) if "." in service else ("notify", service)
        try:
            await hass.services.async_call(
                domain,
                svc,
                {"title": title, "message": message},
                blocking=False,
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
        {
            "title": title,
            "message": message,
            "notification_id": notification_id,
        },
        blocking=False,
    )
