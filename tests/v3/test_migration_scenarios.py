"""Migration scenarios for the breaking PumpSteer V3 configuration schema."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.pumpsteer import async_migrate_entry
from custom_components.pumpsteer.const import (
    CONF_INDOOR_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_TARGET_TEMPERATURE,
)


class FakeConfigEntries:
    """Record config-entry mutations without Home Assistant I/O."""

    def __init__(self) -> None:
        self.updates: list[tuple[object, dict]] = []

    def async_update_entry(self, entry, **changes) -> None:
        self.updates.append((entry, changes))
        for name in ("data", "options", "unique_id", "version", "minor_version"):
            if name in changes:
                setattr(entry, name, changes[name])


def _migrate(entry):
    entries = FakeConfigEntries()
    hass = SimpleNamespace(config_entries=entries)
    result = asyncio.run(async_migrate_entry(hass, entry))
    return result, entries.updates


def test_version_one_migration_keeps_only_three_user_fields() -> None:
    entry = SimpleNamespace(
        version=1,
        data={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "pid_kp": 99.0,
            "weather_entity": "weather.home",
        },
        options={
            "target_temperature": "22.5",
            "house_inertia": 8,
            "brake_ramp_in_minutes": 45,
        },
    )

    migrated, updates = _migrate(entry)

    assert migrated is True
    assert len(updates) == 1
    changes = updates[0][1]
    assert changes["version"] == 3
    assert changes["minor_version"] == 0
    assert changes["options"] == {}
    assert changes["data"] == {
        CONF_INDOOR_ENTITY: "sensor.indoor",
        CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        CONF_TARGET_TEMPERATURE: 22.5,
    }
    assert changes["unique_id"] == "sensor.indoor::sensor.outdoor"


def test_migration_is_idempotent_for_version_three() -> None:
    entry = SimpleNamespace(
        version=3,
        data={
            CONF_INDOOR_ENTITY: "sensor.indoor",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor",
            CONF_TARGET_TEMPERATURE: 21.0,
        },
        options={},
    )

    first, first_updates = _migrate(entry)
    second, second_updates = _migrate(entry)

    assert first is True and second is True
    assert first_updates == []
    assert second_updates == []


def test_version_one_migration_is_noop_on_second_call() -> None:
    entry = SimpleNamespace(
        version=1,
        data={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
        },
        options={},
    )
    entries = FakeConfigEntries()
    hass = SimpleNamespace(config_entries=entries)

    assert asyncio.run(async_migrate_entry(hass, entry)) is True
    assert entry.version == 3
    assert asyncio.run(async_migrate_entry(hass, entry)) is True

    assert len(entries.updates) == 1


def test_invalid_legacy_target_uses_safe_default() -> None:
    entry = SimpleNamespace(
        version=1,
        data={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "target_temperature": float("nan"),
        },
        options={},
    )

    migrated, updates = _migrate(entry)

    assert migrated is True
    assert updates[0][1]["data"][CONF_TARGET_TEMPERATURE] == 21.0


def test_migration_refuses_entry_without_critical_sensor_identity() -> None:
    entry = SimpleNamespace(
        version=1,
        data={"indoor_temp_entity": "sensor.indoor"},
        options={"pid_kp": 8.0},
    )

    migrated, updates = _migrate(entry)

    assert migrated is False
    assert updates == []
