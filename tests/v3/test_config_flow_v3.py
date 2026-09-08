"""Focused tests for the PumpSteer V3 configuration contract."""

import asyncio
from types import SimpleNamespace

from custom_components.pumpsteer import async_migrate_entry
from custom_components.pumpsteer.config_flow import (
    PumpSteerConfigFlow,
    PumpSteerOptionsFlow,
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


def options_flow_with_states(entry, *entity_ids: str) -> PumpSteerOptionsFlow:
    flow = PumpSteerOptionsFlow()
    flow.hass = SimpleNamespace(states=States(set(entity_ids)))
    flow.config_entry = entry
    flow.async_create_entry = lambda title="", data=None: {
        "title": title,
        "data": data or {},
    }
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


def test_options_flow_is_available_for_existing_entry() -> None:
    entry = SimpleNamespace(data={}, options={})

    flow = PumpSteerConfigFlow.async_get_options_flow(entry)

    assert isinstance(flow, PumpSteerOptionsFlow)


def test_options_flow_rejects_same_sensor() -> None:
    entry = SimpleNamespace(
        data={
            CONF_INDOOR_ENTITY: "sensor.indoor",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        },
        options={},
    )
    flow = options_flow_with_states(entry, "sensor.temperature")

    errors = flow._validate_input(
        {
            CONF_INDOOR_ENTITY: "sensor.temperature",
            CONF_OUTDOOR_ENTITY: "sensor.temperature",
        }
    )

    assert errors[CONF_OUTDOOR_ENTITY] == "same_sensor"


def test_options_flow_saves_sensor_overrides_and_preserves_other_options() -> None:
    entry = SimpleNamespace(
        data={
            CONF_INDOOR_ENTITY: "sensor.indoor_old",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor_old",
            CONF_TARGET_TEMPERATURE: 21.0,
        },
        options={"future_setting": "keep"},
    )
    flow = options_flow_with_states(
        entry,
        "sensor.indoor_new",
        "sensor.outdoor_new",
    )

    result = asyncio.run(
        flow.async_step_init(
            {
                CONF_INDOOR_ENTITY: "sensor.indoor_new",
                CONF_OUTDOOR_ENTITY: "sensor.outdoor_new",
            }
        )
    )

    assert result["data"] == {
        "future_setting": "keep",
        CONF_INDOOR_ENTITY: "sensor.indoor_new",
        CONF_OUTDOOR_ENTITY: "sensor.outdoor_new",
    }


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
