"""Focused tests for the PumpSteer V3 configuration contract."""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import async_migrate_entry
from custom_components.pumpsteer.config_flow import (
    PumpSteerConfigFlow,
    PumpSteerOptionsFlow,
    _entry_unique_id,
)
from custom_components.pumpsteer.const import (
    CONF_INDOOR_ENTITY,
    CONF_OHMON_MQTT_BASE_TOPIC,
    CONF_OHMON_WATCHDOG_CONFIRMED,
    CONF_OUTDOOR_ENTITY,
    CONF_OUTPUT_MODE,
    CONF_TARGET_TEMPERATURE,
    OUTPUT_MODE_OHMON_MQTT,
    OUTPUT_MODE_SHADOW,
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


class ConfigEntries:
    def __init__(self, entries=()) -> None:
        self.entries = list(entries)

    def async_entries(self, domain: str):
        assert domain == "pumpsteer"
        return self.entries


def options_flow_with_states(entry, *entity_ids: str) -> PumpSteerOptionsFlow:
    flow = PumpSteerOptionsFlow()
    flow.hass = SimpleNamespace(states=States(set(entity_ids)))
    # Home Assistant injects the config entry before running an options flow.
    flow._config_entry = entry
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


def test_unique_id_is_stable_entry_identity_not_sensor_pair() -> None:
    assert _entry_unique_id("ABC-123") == "pumpsteer-v3:abc-123"


def test_options_flow_is_available_for_existing_entry() -> None:
    entry = SimpleNamespace(data={}, options={})

    flow = PumpSteerConfigFlow.async_get_options_flow(entry)

    assert isinstance(flow, PumpSteerOptionsFlow)


def test_options_flow_rejects_same_sensor() -> None:
    entry = SimpleNamespace(
        entry_id="entry-1",
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
        entry_id="entry-1",
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
        CONF_OUTPUT_MODE: OUTPUT_MODE_SHADOW,
        CONF_OHMON_MQTT_BASE_TOPIC: "",
        CONF_OHMON_WATCHDOG_CONFIRMED: False,
    }


def test_options_enable_active_ohmon_only_with_concrete_topic_and_watchdog() -> None:
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            CONF_INDOOR_ENTITY: "sensor.indoor",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        },
        options={},
    )
    flow = options_flow_with_states(entry, "sensor.indoor", "sensor.outdoor")

    result = asyncio.run(
        flow.async_step_init(
            {
                CONF_INDOOR_ENTITY: "sensor.indoor",
                CONF_OUTDOOR_ENTITY: "sensor.outdoor",
                CONF_OUTPUT_MODE: OUTPUT_MODE_OHMON_MQTT,
                CONF_OHMON_MQTT_BASE_TOPIC: " ohmonwifiplus/123456/ ",
                CONF_OHMON_WATCHDOG_CONFIRMED: True,
            }
        )
    )

    assert result["data"][CONF_OUTPUT_MODE] == OUTPUT_MODE_OHMON_MQTT
    assert result["data"][CONF_OHMON_MQTT_BASE_TOPIC] == ("ohmonwifiplus/123456/")
    assert result["data"][CONF_OHMON_WATCHDOG_CONFIRMED] is True


@pytest.mark.parametrize(
    ("topic", "watchdog", "field"),
    [
        ("ohmonwifiplus/123456", True, CONF_OHMON_MQTT_BASE_TOPIC),
        ("ohmonwifiplus/+/", True, CONF_OHMON_MQTT_BASE_TOPIC),
        (
            "ohmonwifiplus/123456/",
            False,
            CONF_OHMON_WATCHDOG_CONFIRMED,
        ),
    ],
)
def test_options_reject_unsafe_active_ohmon_configuration(
    topic: str, watchdog: bool, field: str
) -> None:
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            CONF_INDOOR_ENTITY: "sensor.indoor",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        },
        options={},
    )
    flow = options_flow_with_states(entry, "sensor.indoor", "sensor.outdoor")

    errors = flow._validate_input(
        {
            CONF_INDOOR_ENTITY: "sensor.indoor",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor",
            CONF_OUTPUT_MODE: OUTPUT_MODE_OHMON_MQTT,
            CONF_OHMON_MQTT_BASE_TOPIC: topic,
            CONF_OHMON_WATCHDOG_CONFIRMED: watchdog,
        }
    )

    assert field in errors


def test_setup_rejects_sensor_pair_owned_by_an_existing_entry() -> None:
    existing = SimpleNamespace(
        entry_id="existing",
        data={
            CONF_INDOOR_ENTITY: "sensor.indoor",
            CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        },
        options={},
    )
    flow = flow_with_states("sensor.indoor", "sensor.outdoor")
    flow.hass.config_entries = ConfigEntries([existing])
    flow.async_show_form = lambda **kwargs: kwargs

    result = asyncio.run(
        flow.async_step_user(
            {
                CONF_INDOOR_ENTITY: "sensor.indoor",
                CONF_OUTDOOR_ENTITY: "sensor.outdoor",
                CONF_TARGET_TEMPERATURE: 21.0,
            }
        )
    )

    assert result["errors"]["base"] == "already_configured"


def test_successful_setup_uses_stable_identity_namespace(monkeypatch) -> None:
    flow = flow_with_states("sensor.indoor", "sensor.outdoor")
    flow.hass.config_entries = ConfigEntries()
    captured = []

    async def set_unique_id(unique_id: str) -> None:
        captured.append(unique_id)

    flow.async_set_unique_id = set_unique_id
    monkeypatch.setattr(
        "custom_components.pumpsteer.config_flow.uuid4",
        lambda: SimpleNamespace(hex="fixed-entry-identity"),
    )

    result = asyncio.run(
        flow.async_step_user(
            {
                CONF_INDOOR_ENTITY: "sensor.indoor",
                CONF_OUTDOOR_ENTITY: "sensor.outdoor",
                CONF_TARGET_TEMPERATURE: 21.0,
            }
        )
    )

    assert captured == ["pumpsteer-v3:fixed-entry-identity"]
    assert result["data"][CONF_INDOOR_ENTITY] == "sensor.indoor"


def test_duplicate_check_uses_existing_option_overrides() -> None:
    existing = SimpleNamespace(
        entry_id="existing",
        data={
            CONF_INDOOR_ENTITY: "sensor.old_indoor",
            CONF_OUTDOOR_ENTITY: "sensor.old_outdoor",
        },
        options={
            CONF_INDOOR_ENTITY: "sensor.new_indoor",
            CONF_OUTDOOR_ENTITY: "sensor.new_outdoor",
        },
    )
    flow = flow_with_states("sensor.new_indoor", "sensor.new_outdoor")
    flow.hass.config_entries = ConfigEntries([existing])
    flow.async_show_form = lambda **kwargs: kwargs

    result = asyncio.run(
        flow.async_step_user(
            {
                CONF_INDOOR_ENTITY: "sensor.new_indoor",
                CONF_OUTDOOR_ENTITY: "sensor.new_outdoor",
                CONF_TARGET_TEMPERATURE: 21.0,
            }
        )
    )

    assert result["errors"]["base"] == "already_configured"


def test_options_reject_pair_owned_by_another_entry() -> None:
    current = SimpleNamespace(
        entry_id="current",
        unique_id="pumpsteer-v3:current",
        data={
            CONF_INDOOR_ENTITY: "sensor.current_indoor",
            CONF_OUTDOOR_ENTITY: "sensor.current_outdoor",
        },
        options={},
    )
    other = SimpleNamespace(
        entry_id="other",
        data={
            CONF_INDOOR_ENTITY: "sensor.other_indoor",
            CONF_OUTDOOR_ENTITY: "sensor.other_outdoor",
        },
        options={},
    )
    flow = options_flow_with_states(
        current,
        "sensor.other_indoor",
        "sensor.other_outdoor",
    )
    flow.hass.config_entries = ConfigEntries([current, other])
    flow.async_show_form = lambda **kwargs: kwargs

    result = asyncio.run(
        flow.async_step_init(
            {
                CONF_INDOOR_ENTITY: "sensor.other_indoor",
                CONF_OUTDOOR_ENTITY: "sensor.other_outdoor",
            }
        )
    )

    assert result["errors"]["base"] == "already_configured"
    assert current.unique_id == "pumpsteer-v3:current"


def test_v2_migration_keeps_sources_but_discards_tuning() -> None:
    updates = {}

    class Entries:
        def async_update_entry(self, entry, **kwargs):
            updates.update(kwargs)

    hass = SimpleNamespace(config_entries=Entries())
    entry = SimpleNamespace(
        entry_id="legacy-entry",
        version=1,
        minor_version=0,
        data={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "pid_kp": 99,
        },
        options={"house_inertia": 8},
    )

    assert asyncio.run(async_migrate_entry(hass, entry))
    assert updates["version"] == 3
    assert updates["minor_version"] == 1
    assert updates["unique_id"] == "pumpsteer-v3:legacy-entry"
    assert updates["data"] == {
        CONF_INDOOR_ENTITY: "sensor.indoor",
        CONF_OUTDOOR_ENTITY: "sensor.outdoor",
        CONF_TARGET_TEMPERATURE: 21.0,
    }
    assert updates["options"] == {}
