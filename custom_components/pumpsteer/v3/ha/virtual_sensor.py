"""Home Assistant sensor exposing the supervised V3 virtual outdoor temperature."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import DOMAIN, INTEGRATION_VERSION, PumpSteerEntryData


class PumpSteerVirtualOutdoorSensor(CoordinatorEntity, SensorEntity):
    """Expose the final supervised virtual outdoor temperature used by V3."""

    _attr_has_entity_name = True
    _attr_name = "Virtual outdoor temperature"
    _attr_icon = "mdi:thermometer-lines"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"

    def __init__(self, entry: ConfigEntry, data: PumpSteerEntryData) -> None:
        super().__init__(data.coordinator)
        self._runtime = data.runtime
        self._attr_unique_id = f"{entry.entry_id}_virtual_outdoor_temperature"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="PumpSteer",
            model="V3 Virtual Outdoor Temperature Controller",
            sw_version=INTEGRATION_VERSION,
        )

    @property
    def native_value(self) -> float | None:
        """Return the final value after safety supervision and quantization."""
        latest = self._runtime.latest
        if latest is None:
            return None
        return round(float(latest.supervised.value), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose explainable context without duplicating controller authority."""
        latest = self._runtime.latest
        if latest is None:
            return {
                "mode": "initializing",
                "target_temperature": self._runtime.config.target_temperature,
                "saving_level": self._runtime.config.saving_level,
            }

        decision = latest.supervised.decision
        observation = latest.observation
        engine_result = getattr(latest, "engine_result", None)
        preheat_plan = getattr(engine_result, "preheat_plan", None)
        return {
            "mode": str(decision.state.value),
            "real_outdoor_temperature": (
                round(float(observation.outdoor.value), 2)
                if observation is not None
                else None
            ),
            "indoor_temperature": (
                round(float(observation.indoor.value), 2)
                if observation is not None
                else None
            ),
            "target_temperature": self._runtime.config.target_temperature,
            "saving_level": self._runtime.config.saving_level,
            "heating_request": round(float(decision.heating_request), 2),
            "curtailment": round(float(decision.curtailment), 2),
            "reason_codes": [str(reason.value) for reason in decision.reason_codes],
            "fallback_active": bool(latest.supervised.fallback_active),
            "physical_output_active": bool(latest.supervised.apply_physical),
            "preheat_active": bool(preheat_plan and preheat_plan.active),
            "preheat_reason": (
                str(preheat_plan.reason.value) if preheat_plan is not None else None
            ),
            "preheat_target_temperature": (
                round(float(preheat_plan.effective_target_temperature), 2)
                if preheat_plan is not None and preheat_plan.active
                else None
            ),
            "predicted_min_indoor_temperature": (
                round(float(preheat_plan.predicted_min_indoor_temperature), 2)
                if preheat_plan is not None
                and preheat_plan.predicted_min_indoor_temperature is not None
                else None
            ),
        }


async def async_setup_virtual_sensor(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the single V3 virtual outdoor temperature sensor."""
    del hass
    data: PumpSteerEntryData = entry.runtime_data
    async_add_entities([PumpSteerVirtualOutdoorSensor(entry, data)])
