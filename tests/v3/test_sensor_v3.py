"""Focused tests for the PumpSteer V3 virtual outdoor temperature sensor."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace


coordinator_module = types.ModuleType("homeassistant.helpers.update_coordinator")


class CoordinatorEntity:
    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator


coordinator_module.CoordinatorEntity = CoordinatorEntity
sys.modules["homeassistant.helpers.update_coordinator"] = coordinator_module

ha_const = sys.modules["homeassistant.const"]
ha_const.UnitOfTemperature = SimpleNamespace(CELSIUS="°C")

from custom_components.pumpsteer.const import PumpSteerEntryData  # noqa: E402
from custom_components.pumpsteer.v3.ha.virtual_sensor import (  # noqa: E402
    PumpSteerVirtualOutdoorSensor,
)


class Runtime:
    def __init__(self, latest) -> None:
        self.latest = latest
        self.config = SimpleNamespace(target_temperature=21.0, saving_level=3)


def _latest():
    observation = SimpleNamespace(
        indoor=SimpleNamespace(value=20.4),
        outdoor=SimpleNamespace(value=-4.2),
    )
    decision = SimpleNamespace(
        state=SimpleNamespace(value="comfort"),
        heating_request=1.4,
        curtailment=0.0,
        reason_codes=(SimpleNamespace(value="comfort_below_target"),),
    )
    supervised = SimpleNamespace(
        value=-5.5,
        decision=decision,
        fallback_active=False,
        apply_physical=True,
    )
    return SimpleNamespace(observation=observation, supervised=supervised)


def test_virtual_sensor_exposes_supervised_output_and_context() -> None:
    runtime = Runtime(_latest())
    entry = SimpleNamespace(entry_id="entry")
    data = PumpSteerEntryData(runtime=runtime, coordinator=object())

    entity = PumpSteerVirtualOutdoorSensor(entry, data)

    assert entity.native_value == -5.5
    assert entity._attr_unique_id == "entry_virtual_outdoor_temperature"
    attrs = entity.extra_state_attributes
    assert attrs["mode"] == "comfort"
    assert attrs["real_outdoor_temperature"] == -4.2
    assert attrs["indoor_temperature"] == 20.4
    assert attrs["target_temperature"] == 21.0
    assert attrs["saving_level"] == 3
    assert attrs["heating_request"] == 1.4
    assert attrs["curtailment"] == 0.0
    assert attrs["reason_codes"] == ["comfort_below_target"]
    assert attrs["fallback_active"] is False
    assert attrs["physical_output_active"] is True


def test_virtual_sensor_is_unavailable_until_first_runtime_cycle() -> None:
    runtime = Runtime(None)
    entry = SimpleNamespace(entry_id="entry")
    data = PumpSteerEntryData(runtime=runtime, coordinator=object())

    entity = PumpSteerVirtualOutdoorSensor(entry, data)

    assert entity.native_value is None
    assert entity.extra_state_attributes == {
        "mode": "initializing",
        "target_temperature": 21.0,
        "saving_level": 3,
    }
