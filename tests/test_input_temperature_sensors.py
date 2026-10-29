"""Read-only input sensors follow qualified control-cycle data, offline."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_safe_mode_output import setup_sensor  # noqa: F401
from test_temperature_input_safety import _report, control  # noqa: F401

from custom_components.pumpsteer import sensor as sensor_module


@pytest.fixture
def temperatures(request):
    controller, states, clock = request.getfixturevalue("control")
    sensor_class = getattr(sensor_module, "PumpSteerInputTemperatureSensor", None)
    assert sensor_class is not None, "The two input temperature sensors are missing"
    entities = [
        sensor_class(controller, key)
        for key in ("indoor_temperature", "outdoor_temperature")
    ]
    writes = [[], []]
    for index, entity in enumerate(entities):
        entity.hass = controller.hass
        entity.async_write_ha_state = lambda i=index, e=entity: writes[i].append(
            e.native_value
        )
        asyncio.run(entity.async_added_to_hass())
    return controller, states, clock, entities, writes


def test_values_match_control_snapshot_without_independent_reads(temperatures):
    controller, states, clock, entities, writes = temperatures
    states["sensor.indoor"].state = "20.125"
    states["sensor.outdoor"].state = "0"
    asyncio.run(controller.async_update())
    assert [e.native_value for e in entities] == [20.125, 0.0]
    assert [e.available for e in entities] == [True, True]
    assert controller.extra_state_attributes["indoor_temperature"] == 20.125
    assert controller.extra_state_attributes["outdoor_temperature"] == 0.0
    # A later source change must not become a separate observation by these entities.
    states["sensor.indoor"].state = "25"
    assert entities[0].native_value == 20.125
    states["sensor.indoor"].state = "20.125"
    clock[0] += timedelta(minutes=1)
    asyncio.run(controller.async_update())
    assert writes == [[20.125], [0.0]]  # No timestamp/mode attribute churn.


@pytest.mark.parametrize("index,key", [(0, "indoor"), (1, "outdoor")])
@pytest.mark.parametrize("value", ["unknown", "unavailable", "nan", "inf", "bad"])
def test_loss_is_per_input_and_recovers(temperatures, index, key, value):
    controller, states, _, entities, _ = temperatures
    asyncio.run(controller.async_update())
    states[f"sensor.{key}"].state = value
    asyncio.run(controller.async_update())
    assert entities[index].native_value is None
    assert not entities[index].available
    assert entities[1 - index].available
    states[f"sensor.{key}"].state = "0"
    asyncio.run(controller.async_update())
    assert entities[index].available
    assert entities[index].native_value == 0.0


def test_start_restore_reload_and_fresh_report(temperatures, monkeypatch):
    controller, states, clock, entities, _ = temperatures
    controller.hass.is_running = False
    controller.hass.bus = SimpleNamespace(async_listen_once=lambda *args: lambda: None)
    controller._config_entry.add_update_listener = lambda callback: lambda: None

    async def last_state():
        return SimpleNamespace(
            state="-12",
            attributes={"indoor_temperature": 28, "outdoor_temperature": 12},
        )

    async def no_extra():
        return None

    monkeypatch.setattr(controller, "async_get_last_state", last_state)
    monkeypatch.setattr(
        controller, "async_get_last_extra_data", no_extra, raising=False
    )
    asyncio.run(controller.async_added_to_hass())
    assert [e.available for e in entities] == [False, False]
    controller.hass.is_running = True
    _report(states, clock, restored=True)
    asyncio.run(controller._handle_ha_started(None))
    assert [e.available for e in entities] == [False, False]
    clock[0] += timedelta(seconds=1)
    _report(states, clock)
    asyncio.run(controller.async_update())
    assert [e.native_value for e in entities] == [21.0, -3.3]
    asyncio.run(controller.async_will_remove_from_hass())
    assert [e.available for e in entities] == [False, False]
    # A reload uses a new controller and the same per-entry entity identities.
    reloaded = sensor_module.PumpSteerSensor(controller.hass, controller._config_entry)
    reloaded.async_write_ha_state = lambda: None
    monkeypatch.setattr(reloaded, "async_get_last_extra_data", no_extra, raising=False)
    asyncio.run(reloaded.async_added_to_hass())
    replacements = [
        sensor_module.PumpSteerInputTemperatureSensor(reloaded, e._key)
        for e in entities
    ]
    for entity in replacements:
        entity.hass = controller.hass
        entity.async_write_ha_state = lambda: None
        asyncio.run(entity.async_added_to_hass())
    assert [e.available for e in replacements] == [False, False]
    assert [e._attr_unique_id for e in replacements] == [
        e._attr_unique_id for e in entities
    ]
    clock[0] += timedelta(seconds=1)
    _report(states, clock)
    asyncio.run(reloaded.async_update())
    assert [e.native_value for e in replacements] == [21.0, -3.3]


def test_interrupted_cycle_and_exception_clear_values(temperatures, monkeypatch):
    controller, states, _, entities, _ = temperatures
    asyncio.run(controller.async_update())

    async def interrupted():
        states["sensor.outdoor"].state = "unavailable"
        return []

    monkeypatch.setattr(controller, "_forecast_temps", interrupted)
    asyncio.run(controller.async_update())
    assert [e.available for e in entities] == [False, False]
    states["sensor.outdoor"].state = "-3.3"

    async def failure():
        raise RuntimeError("synthetic calculation failure")

    monkeypatch.setattr(controller, "_forecast_temps", failure)
    asyncio.run(controller.async_update())
    assert [e.available for e in entities] == [False, False]


def test_entity_contract_and_translated_names(temperatures):
    controller, _, _, entities, _ = temperatures
    assert controller.unique_id == "safe-mode-test"
    assert controller._attr_translation_key == "control_temperature"
    assert "friendly_name" not in controller.extra_state_attributes
    assert [e._attr_unique_id for e in entities] == [
        "safe-mode-test_indoor_temperature",
        "safe-mode-test_outdoor_temperature",
    ]
    for entity in entities:
        assert entity._attr_device_info is controller._attr_device_info
        assert entity._attr_device_info["identifiers"] == {
            ("pumpsteer", "safe-mode-test")
        }
        assert entity._attr_native_unit_of_measurement == "°C"
        assert entity._attr_device_class == "temperature"
        assert entity._attr_state_class == "measurement"
        assert entity._attr_should_poll is False
        assert entity._attr_has_entity_name is True
    root = Path(sensor_module.__file__).parent
    for filename, names in (
        (
            "strings.json",
            ["Indoor temperature", "Outdoor temperature", "Control temperature"],
        ),
        (
            "translations/en.json",
            ["Indoor temperature", "Outdoor temperature", "Control temperature"],
        ),
        (
            "translations/sv.json",
            ["Inomhustemperatur", "Utomhustemperatur", "Styrtemperatur"],
        ),
    ):
        translations = json.loads((root / filename).read_text())["entity"]["sensor"]
        assert [
            translations[key]["name"]
            for key in (
                "indoor_temperature",
                "outdoor_temperature",
                "control_temperature",
            )
        ] == names


def test_source_change_during_update_does_not_publish_old_selection(
    temperatures, monkeypatch
):
    controller, states, _, entities, _ = temperatures
    asyncio.run(controller.async_update())
    states["sensor.other"] = SimpleNamespace(state="-8", attributes={})

    async def switch_source():
        controller._config_entry.options["real_outdoor_entity"] = "sensor.other"
        return []

    monkeypatch.setattr(controller, "_forecast_temps", switch_source)
    asyncio.run(controller.async_update())
    assert [e.available for e in entities] == [False, False]
    asyncio.run(controller.async_update())
    assert [e.native_value for e in entities] == [21.0, -8.0]


def test_cancelled_update_clears_values_and_recovers(temperatures, monkeypatch):
    controller, _, _, entities, _ = temperatures
    asyncio.run(controller.async_update())

    async def cancelled():
        raise asyncio.CancelledError

    monkeypatch.setattr(controller, "_forecast_temps", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(controller.async_update())
    assert [e.available for e in entities] == [False, False]

    async def recovered():
        return []

    monkeypatch.setattr(controller, "_forecast_temps", recovered)
    asyncio.run(controller.async_update())
    assert [e.native_value for e in entities] == [21.0, -3.3]


def test_removed_entity_unsubscribes(temperatures):
    controller, states, _, entities, writes = temperatures
    asyncio.run(controller.async_update())
    asyncio.run(entities[0].async_will_remove_from_hass())
    states["sensor.indoor"].state = "22"
    states["sensor.outdoor"].state = "-4"
    asyncio.run(controller.async_update())
    assert writes == [[21.0], [-3.3, -4.0]]


def test_setup_registers_two_inputs_with_original_controller(request):
    controller, _, _ = request.getfixturevalue("control")
    added = []

    async def executor_job(job):
        pass  # Logging setup is outside the sensor platform contract.

    controller.hass.async_add_executor_job = executor_job

    def add_entities(entities, update_before_add=False):
        assert update_before_add is False
        added.extend(entities)

    asyncio.run(
        sensor_module.async_setup_entry(
            controller.hass, controller._config_entry, add_entities
        )
    )
    assert len(added) == 4
    assert added[0].unique_id == "safe-mode-test"
    assert [e._attr_translation_key for e in added[2:]] == [
        "indoor_temperature",
        "outdoor_temperature",
    ]
    assert all(e._controller is added[0] for e in added[2:])


def test_control_temperature_keeps_legacy_id_suggestion(temperatures):
    controller, _, _, _, _ = temperatures
    # Notification setup precedes entity registration and watches this default ID.
    assert controller.entity_id == "sensor.pumpsteer"
    assert controller.unique_id == "safe-mode-test"


def test_entity_added_mid_cycle_waits_for_completed_snapshot(temperatures, monkeypatch):
    controller, states, _, _, _ = temperatures
    asyncio.run(controller.async_update())
    late_entity = sensor_module.PumpSteerInputTemperatureSensor(
        controller, "outdoor_temperature"
    )
    late_entity.hass = controller.hass
    writes = []
    late_entity.async_write_ha_state = lambda: writes.append(late_entity.native_value)

    async def interrupted():
        await late_entity.async_added_to_hass()
        states["sensor.outdoor"].state = "unavailable"
        return []

    monkeypatch.setattr(controller, "_forecast_temps", interrupted)
    asyncio.run(controller.async_update())
    assert late_entity.native_value is None
    assert writes == []  # Never records a provisional observation.


def test_valid_temperatures_remain_visible_when_prices_missing(
    temperatures, monkeypatch
):
    controller, _, _, entities, _ = temperatures

    async def missing_prices(cfg, now):
        return [], [], 60, 0

    monkeypatch.setattr(controller, "_get_prices", missing_prices)
    asyncio.run(controller.async_update())
    assert [e.native_value for e in entities] == [21.0, -3.3]
    assert [e.available for e in entities] == [True, True]
