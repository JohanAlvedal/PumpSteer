"""Focused tests for the PumpSteer V3 configuration contract."""

import asyncio
from types import SimpleNamespace

from custom_components.pumpsteer import async_migrate_entry
from custom_components.pumpsteer.config_flow import (
    PumpSteerConfigFlow,
    _entry_unique_id,
)
from custom_components.pumpsteer.const import (
    CONF_INDOOR_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_TARGET_TEMPERATURE,
)


class States:
    def __init__(self, entity_ids: set[str]) -> None:
        self.entity_ids = entity_ids

    def get(self, entity_id: str):
        if entity_id in self.entity_ids:
            return SimpleNamespace(state="unavailable")
        return None


def flow_with_states(*entity_ids: str) -> PumpSteerConfigFlow:
    flow = PumpSteerConfigFlow()
    flow.hass = SimpleNamespace(states=States(set(entity_ids)))
    return flow


def test_temporarily_unavailable_registered_state_is_accepted() -> None:
    flow = flow_with_states("sensor.indoor", "sensor.outdoor")

    errors = flow._validate_input(
        {
            CONF_INDOOR_ENTITY: "sensor.indoor",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor",
            CONF_TARGET_TEMPERATURE: 21.0,
        }
    )

    assert errors == {}


def test_same_sensor_is_rejected() -> None:
    flow = flow_with_states("sensor.temperature")

    errors = flow._validate_input(
        {
            CONF_INDOOR_ENTITY: "sensor.temperature",
            CONF_OUTDOOR_ENTITY: "sensor.temperature",
            CONF_TARGET_TEMPERATURE: 21.0,
        }
    )

    assert errors[CONF_OUTDOOR_ENTITY] == "same_sensor"


def test_unique_id_is_deterministic_for_sensor_pair() -> None:
    assert _entry_unique_id("Sensor.Inside", "sensor.OUTSIDE") == (
        "sensor.inside::sensor.outside"
    )


def test_v2_migration_keeps_sources_but_discards_tuning() -> None:
    updates = {}

    class Entries:
        def async_update_entry(self, entry, **kwargs):
            updates.update(kwargs)

    hass = SimpleNamespace(config_entries=Entries())
    entry = SimpleNamespace(
        version=1,
        data={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "pid_kp": 99,
        },
        options={"house_inertia": 8},
    )

    assert asyncio.run(async_migrate_entry(hass, entry))
    assert updates["version"] == 3
    assert updates["data"] == {
        CONF_INDOOR_ENTITY: "sensor.indoor",
        CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        CONF_TARGET_TEMPERATURE: 21.0,
    }
    assert updates["options"] == {}
