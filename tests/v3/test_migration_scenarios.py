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


def test_version_one_is_refused_without_mutating_legacy_configuration() -> None:
    entry = SimpleNamespace(
        entry_id="legacy-one",
        version=1,
        minor_version=0,
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

    assert migrated is False
    assert updates == []
    assert entry.version == 1
    assert entry.options["house_inertia"] == 8


def test_migration_is_idempotent_for_version_three() -> None:
    entry = SimpleNamespace(
        entry_id="current-entry",
        version=3,
        minor_version=1,
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


def test_alpha_three_entry_gets_stable_identity_without_data_changes() -> None:
    data = {
        CONF_INDOOR_ENTITY: "sensor.indoor",
        CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        CONF_TARGET_TEMPERATURE: 21.0,
    }
    options = {CONF_INDOOR_ENTITY: "sensor.indoor_new"}
    entry = SimpleNamespace(
        entry_id="alpha-three-entry",
        unique_id="sensor.indoor::sensor.outdoor",
        version=3,
        minor_version=0,
        data=data,
        options=options,
    )

    migrated, updates = _migrate(entry)

    assert migrated is True
    assert updates == [
        (
            entry,
            {
                "unique_id": "pumpsteer-v3:alpha-three-entry",
                "version": 3,
                "minor_version": 1,
            },
        )
    ]
    assert entry.data is data
    assert entry.options is options


def test_version_one_refusal_is_repeatable_and_non_destructive() -> None:
    entry = SimpleNamespace(
        entry_id="legacy-two",
        version=1,
        minor_version=0,
        data={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
        },
        options={},
    )
    entries = FakeConfigEntries()
    hass = SimpleNamespace(config_entries=entries)

    assert asyncio.run(async_migrate_entry(hass, entry)) is False
    assert asyncio.run(async_migrate_entry(hass, entry)) is False

    assert entry.version == 1
    assert entries.updates == []


def test_invalid_legacy_values_are_left_untouched_for_v2_rollback() -> None:
    entry = SimpleNamespace(
        entry_id="legacy-invalid-target",
        version=1,
        minor_version=0,
        data={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "target_temperature": float("nan"),
        },
        options={},
    )

    migrated, updates = _migrate(entry)

    assert migrated is False
    assert updates == []
    assert entry.data["target_temperature"] != entry.data["target_temperature"]


def test_migration_refuses_entry_without_critical_sensor_identity() -> None:
    entry = SimpleNamespace(
        entry_id="legacy-missing-source",
        version=1,
        minor_version=0,
        data={"indoor_temp_entity": "sensor.indoor"},
        options={"pid_kp": 8.0},
    )

    migrated, updates = _migrate(entry)

    assert migrated is False
    assert updates == []
