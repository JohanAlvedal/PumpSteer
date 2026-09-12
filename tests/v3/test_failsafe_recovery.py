"""Regression tests for recoverable PumpSteer V3 fail-safe behavior."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from custom_components.pumpsteer import sensor as sensor_platform
from custom_components.pumpsteer.v3 import ControlState, Unit
from custom_components.pumpsteer.v3.control.engine import ControlEngine
from custom_components.pumpsteer.v3.ha import PumpSteerRuntime, RawState, RuntimeConfig


NOW = datetime(2026, 9, 12, 6, 0, tzinfo=UTC)
INDOOR = "sensor.indoor"
OUTDOOR = "sensor.outdoor"


class MutableStates:
    """Provide mutable source states so one runtime can recover in place."""

    def __init__(self) -> None:
        self.values: dict[str, RawState] = {}

    def get_state(self, entity_id: str) -> RawState | None:
        return self.values.get(entity_id)

    def set_temperature(self, entity_id: str, value: object, observed_at: datetime) -> None:
        self.values[entity_id] = RawState(
            value=value,
            observed_at=observed_at,
            unit=Unit.CELSIUS,
            source=entity_id,
        )


def test_runtime_recovers_from_startup_failsafe_without_restart() -> None:
    """A transient unavailable source must not latch the runtime in fail-safe."""
    states = MutableStates()
    states.set_temperature(INDOOR, "unavailable", NOW)
    states.set_temperature(OUTDOOR, 4.0, NOW)
    runtime = PumpSteerRuntime(
        config=RuntimeConfig(INDOOR, OUTDOOR, 21.0),
        states=states,
        engine=ControlEngine(),
    )

    failed = asyncio.run(runtime.async_update(NOW))

    assert failed.supervised.decision.state is ControlState.FAILSAFE
    assert failed.supervised.fallback_active is True
    assert runtime.latest is failed

    recovered_at = NOW + timedelta(minutes=1)
    states.set_temperature(INDOOR, 20.5, recovered_at)
    states.set_temperature(OUTDOOR, 4.0, recovered_at)
    recovered = asyncio.run(runtime.async_update(recovered_at))

    assert recovered.error is None
    assert recovered.observation is not None
    assert recovered.supervised.decision.state is ControlState.COMFORT
    assert recovered.supervised.fallback_active is False
    assert runtime.latest is recovered


def test_v3_sensor_platform_does_not_depend_on_legacy_entry_version(monkeypatch) -> None:
    """The V3 branch must always register the V3 virtual sensor platform."""
    calls: list[tuple[object, object, object]] = []

    async def fake_setup(hass, entry, async_add_entities) -> None:
        calls.append((hass, entry, async_add_entities))

    from custom_components.pumpsteer.v3.ha import virtual_sensor

    monkeypatch.setattr(virtual_sensor, "async_setup_virtual_sensor", fake_setup)

    class LegacyVersionEntry:
        version = 1

    hass = object()
    entry = LegacyVersionEntry()
    add_entities = object()

    asyncio.run(sensor_platform.async_setup_entry(hass, entry, add_entities))

    assert calls == [(hass, entry, add_entities)]
