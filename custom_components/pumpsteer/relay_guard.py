"""Optional Ohmigo Active/Bypass relay recovery guard."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta
from typing import Any, Callable

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import DOMAIN, OHMIGO_RELAY_ENTITY

_LOGGER = logging.getLogger(__name__)

_RELAY_GUARD_UNIQUE_KEY = "ohmigo_relay_guard"
_OHMIGO_PUSH_UNIQUE_KEY = "ohmigo_enabled"

_STABILIZE_SECONDS = 2
_VERIFY_SECONDS = 3
_MAX_ATTEMPTS = 3
_SAFETY_CHECK_INTERVAL = timedelta(minutes=5)

_STATUS_DISARMED = "disarmed"
_STATUS_INHIBITED = "inhibited_by_push"
_STATUS_WAITING = "relay_unavailable"
_STATUS_HEALTHY = "healthy"
_STATUS_STABILIZING = "stabilizing"
_STATUS_RECOVERING = "recovering"
_STATUS_FAILED = "failed"


def configured_relay_entity(entry: ConfigEntry) -> str:
    """Return the configured Ohmigo relay entity, or an empty string."""
    cfg = {**entry.data, **entry.options}
    return str(cfg.get(OHMIGO_RELAY_ENTITY, "") or "").strip()


def create_relay_guard(
    hass: HomeAssistant, entry: ConfigEntry
) -> OhmigoRelayGuard | None:
    """Create a relay guard only when an Ohmigo relay is configured."""
    relay_entity = configured_relay_entity(entry)
    if not relay_entity:
        return None
    return OhmigoRelayGuard(hass, entry, relay_entity)


class OhmigoRelayGuard:
    """Keep an explicitly configured Ohmigo relay Active when it should be."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        relay_entity: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.relay_entity = relay_entity

        self._status = _STATUS_DISARMED
        self._attempts = 0
        self._last_recovery: str | None = None
        self._last_failure: str | None = None

        self._started = False
        self._unsubscribers: list[Callable[[], None]] = []
        self._listeners: set[Callable[[], None]] = set()
        self._recovery_task: asyncio.Task[Any] | None = None

    @property
    def status(self) -> str:
        """Return the current relay-guard status."""
        return self._status

    @property
    def diagnostics(self) -> dict[str, Any]:
        """Return lightweight diagnostics for the Relay Guard switch."""
        relay_state = self.hass.states.get(self.relay_entity)
        push_entity = self._switch_entity_id(_OHMIGO_PUSH_UNIQUE_KEY)
        push_state = self.hass.states.get(push_entity) if push_entity else None

        return {
            "status": self._status,
            "relay_entity": self.relay_entity,
            "relay_state": relay_state.state if relay_state is not None else None,
            "ohmigo_push_state": (
                push_state.state if push_state is not None else None
            ),
            "recovery_attempts": self._attempts,
            "last_recovery": self._last_recovery,
            "last_failure": self._last_failure,
        }

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a diagnostics update listener."""
        self._listeners.add(listener)

        def _remove_listener() -> None:
            self._listeners.discard(listener)

        return _remove_listener

    def async_start(self) -> None:
        """Start state, startup and periodic monitoring."""
        if self._started:
            return

        self._started = True
        watched_entities = [self.relay_entity]
        push_entity = self._switch_entity_id(_OHMIGO_PUSH_UNIQUE_KEY)
        if push_entity:
            watched_entities.append(push_entity)

        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass,
                watched_entities,
                self._on_watched_state_change,
            )
        )
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._on_periodic_check,
                _SAFETY_CHECK_INTERVAL,
            )
        )
        self._unsubscribers.append(
            self.hass.bus.async_listen_once(
                "homeassistant_started",
                self._on_homeassistant_started,
            )
        )

        if self.hass.is_running:
            self._schedule_check("integration_setup")

        _LOGGER.debug(
            "Ohmigo Relay Guard monitoring %s", self.relay_entity
        )

    async def async_stop(self) -> None:
        """Stop monitoring and cancel any in-flight recovery."""
        self._started = False

        while self._unsubscribers:
            unsubscribe = self._unsubscribers.pop()
            with suppress(Exception):
                unsubscribe()

        task = self._recovery_task
        self._recovery_task = None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        self._listeners.clear()

    @callback
    def async_guard_state_changed(self) -> None:
        """Re-evaluate immediately when the user arms/disarms the guard."""
        self._schedule_check("guard_state")

    @callback
    def _on_watched_state_change(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        self._schedule_check("state_change")

    @callback
    def _on_periodic_check(self, now) -> None:
        del now
        self._schedule_check("periodic")

    @callback
    def _on_homeassistant_started(self, event) -> None:
        del event
        self._schedule_check("ha_start")

    @callback
    def _schedule_check(self, reason: str) -> None:
        if not self._started:
            return
        if self._recovery_task is not None and not self._recovery_task.done():
            return

        task = self.hass.async_create_task(self.async_check(reason))
        self._recovery_task = task
        task.add_done_callback(self._recovery_done)

    @callback
    def _recovery_done(self, task: asyncio.Task[Any]) -> None:
        if self._recovery_task is task:
            self._recovery_task = None

        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            _LOGGER.exception("Ohmigo Relay Guard check failed unexpectedly")

    async def async_check(self, reason: str = "manual") -> str:
        """Evaluate the guard and recover an explicit OFF relay if eligible."""
        eligibility = self._eligibility()
        if eligibility != _STATUS_RECOVERING:
            self._set_status(eligibility)
            return eligibility

        await self._recover(reason)
        return self._status

    async def _recover(self, reason: str) -> None:
        self._attempts = 0
        self._set_status(_STATUS_STABILIZING)
        await asyncio.sleep(_STABILIZE_SECONDS)

        eligibility = self._eligibility()
        if eligibility != _STATUS_RECOVERING:
            self._set_status(eligibility)
            return

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            eligibility = self._eligibility()
            if eligibility != _STATUS_RECOVERING:
                self._set_status(eligibility)
                return

            self._attempts = attempt
            self._set_status(_STATUS_RECOVERING)

            try:
                await self.hass.services.async_call(
                    "switch",
                    "turn_on",
                    {"entity_id": self.relay_entity},
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Ohmigo Relay Guard turn_on attempt %d failed for %s: %s",
                    attempt,
                    self.relay_entity,
                    err,
                )

            await asyncio.sleep(_VERIFY_SECONDS)

            if self._relay_state() == "on":
                timestamp = dt_util.now().isoformat()
                self._last_recovery = timestamp
                self._last_failure = None
                self._set_status(_STATUS_HEALTHY)
                self._log_recovery(reason, attempt)
                return

        eligibility = self._eligibility()
        if eligibility != _STATUS_RECOVERING:
            self._set_status(eligibility)
            return

        self._last_failure = dt_util.now().isoformat()
        self._set_status(_STATUS_FAILED)
        _LOGGER.error(
            "Ohmigo Relay Guard could not restore %s after %d attempts",
            self.relay_entity,
            _MAX_ATTEMPTS,
        )

    def _eligibility(self) -> str:
        if not self._guard_armed():
            return _STATUS_DISARMED
        if not self._ohmigo_push_enabled():
            return _STATUS_INHIBITED

        relay_state = self._relay_state()
        if relay_state == "on":
            return _STATUS_HEALTHY
        if relay_state == "off":
            return _STATUS_RECOVERING
        return _STATUS_WAITING

    def _relay_state(self) -> str | None:
        state = self.hass.states.get(self.relay_entity)
        return state.state if state is not None else None

    def _guard_armed(self) -> bool:
        guard_entity = self._switch_entity_id(_RELAY_GUARD_UNIQUE_KEY)
        if not guard_entity:
            return False
        state = self.hass.states.get(guard_entity)
        return state is not None and state.state == "on"

    def _ohmigo_push_enabled(self) -> bool:
        push_entity = self._switch_entity_id(_OHMIGO_PUSH_UNIQUE_KEY)
        if not push_entity:
            return False
        state = self.hass.states.get(push_entity)
        return state is not None and state.state == "on"

    def _switch_entity_id(self, unique_key: str) -> str | None:
        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            "switch",
            DOMAIN,
            f"{self.entry.entry_id}_{unique_key}",
        )

    def _set_status(self, status: str) -> None:
        if status == self._status:
            return
        self._status = status
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.debug(
                    "Ohmigo Relay Guard diagnostics listener failed",
                    exc_info=True,
                )

    def _log_recovery(self, reason: str, attempt: int) -> None:
        _LOGGER.info(
            "Ohmigo Relay Guard restored %s on attempt %d (trigger=%s)",
            self.relay_entity,
            attempt,
            reason,
        )

        try:
            from homeassistant.components import logbook

            logbook.async_log_entry(
                self.hass,
                name="PumpSteer",
                message=(
                    "Ohmigo Relay Guard restored Active "
                    f"on attempt {attempt} (trigger={reason})"
                ),
                domain=DOMAIN,
                entity_id=self.relay_entity,
            )
        except Exception:
            _LOGGER.debug("Could not write Relay Guard logbook entry", exc_info=True)
