"""Tests for Home Assistant state timestamp handling in PumpSteer V3."""

import sys
import types
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace


update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")


class DataUpdateCoordinator:
    """Minimal coordinator stub required to import the HA adapter."""

    @classmethod
    def __class_getitem__(cls, _item):
        return cls


update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

from custom_components.pumpsteer.v3.ha.coordinator import (  # noqa: E402
    HomeAssistantStateProvider,
)


NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)


class FakeStateMachine:
    """Minimal Home Assistant state-machine stand-in."""

    def __init__(self, state) -> None:
        self._state = state

    def get(self, _entity_id: str):
        return self._state


def test_state_provider_prefers_last_reported_over_last_updated() -> None:
    """An unchanged but recently reported sensor must remain fresh."""
    state = SimpleNamespace(
        state="12.5",
        attributes={"unit_of_measurement": "°C"},
        last_updated=NOW - timedelta(minutes=30),
        last_reported=NOW - timedelta(seconds=20),
    )
    hass = SimpleNamespace(states=FakeStateMachine(state))

    raw = HomeAssistantStateProvider(hass).get_state("sensor.outdoor")

    assert raw is not None
    assert raw.observed_at == state.last_reported


def test_state_provider_falls_back_to_last_updated_when_last_reported_missing() -> None:
    """Older Home Assistant state objects remain supported."""
    state = SimpleNamespace(
        state="12.5",
        attributes={"unit_of_measurement": "°C"},
        last_updated=NOW - timedelta(seconds=20),
    )
    hass = SimpleNamespace(states=FakeStateMachine(state))

    raw = HomeAssistantStateProvider(hass).get_state("sensor.outdoor")

    assert raw is not None
    assert raw.observed_at == state.last_updated
