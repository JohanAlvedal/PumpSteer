"""Home Assistant coordinator adapter for the PumpSteer V3 runtime."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..enums import Unit
from .runtime import PumpSteerRuntime, RawState, RuntimeResult

_LOGGER = logging.getLogger(__name__)


def _normalize_state_value(value: object) -> object:
    """Convert numeric Home Assistant state strings at the platform boundary."""
    if not isinstance(value, str):
        return value
    try:
        return float(value)
    except ValueError:
        return value


class HomeAssistantStateProvider:
    """Translate Home Assistant states at the platform boundary."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def get_state(self, entity_id: str) -> RawState | None:
        """Return one state in the platform-neutral representation."""
        state = self._hass.states.get(entity_id)
        if state is None:
            return None
        unit = state.attributes.get("unit_of_measurement", Unit.CELSIUS.value)
        observed_at = getattr(state, "last_reported", None) or state.last_updated
        return RawState(
            value=_normalize_state_value(state.state),
            observed_at=observed_at,
            unit=unit,
            source=entity_id,
        )


class PumpSteerDataUpdateCoordinator(DataUpdateCoordinator[RuntimeResult]):
    """Combine periodic watchdog updates with event-driven source updates."""

    def __init__(self, hass: HomeAssistant, runtime: PumpSteerRuntime) -> None:
        self.runtime = runtime
        super().__init__(
            hass,
            logger=_LOGGER,
            name="PumpSteer V3 runtime",
            update_interval=runtime.config.update_interval,
        )

    async def _async_update_data(self) -> RuntimeResult:
        return await self.runtime.async_update(datetime.now(UTC))

    @callback
    def async_start_source_tracking(self) -> Any:
        """Refresh promptly when either required source changes."""
        entity_ids = (
            self.runtime.config.indoor_entity,
            self.runtime.config.outdoor_entity,
        )

        @callback
        def _source_changed(_event: Any) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        return async_track_state_change_event(self.hass, entity_ids, _source_changed)
