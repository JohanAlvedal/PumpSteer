"""PumpSteer V3 climate entity."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_TARGET_TEMPERATURE,
    DOMAIN,
    MAX_TARGET_TEMPERATURE,
    MIN_TARGET_TEMPERATURE,
    PumpSteerEntryData,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the single V3 climate entity."""
    data: PumpSteerEntryData = entry.runtime_data
    async_add_entities([PumpSteerClimate(hass, entry, data)])


class PumpSteerClimate(CoordinatorEntity, ClimateEntity):
    """Expose the V3 room target and shadow control request."""

    _attr_has_entity_name = True
    _attr_translation_key = "thermostat"
    _attr_hvac_modes = [HVACMode.AUTO]
    _attr_hvac_mode = HVACMode.AUTO
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = MIN_TARGET_TEMPERATURE
    _attr_max_temp = MAX_TARGET_TEMPERATURE

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        data: PumpSteerEntryData,
    ) -> None:
        super().__init__(data.coordinator)
        self._hass = hass
        self._entry = entry
        self._runtime = data.runtime
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="PumpSteer",
            model="V3 Virtual Outdoor Temperature Controller",
        )

    @property
    def current_temperature(self) -> float | None:
        """Return the latest validated indoor temperature."""
        latest = self._runtime.latest
        if latest is None or latest.observation is None:
            return None
        return latest.observation.indoor.value

    @property
    def target_temperature(self) -> float:
        """Return the user comfort target."""
        return self._runtime.config.target_temperature

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Expose AUTO only; bypass needs a separate controller contract."""
        return [HVACMode.AUTO]

    @property
    def hvac_mode(self) -> HVACMode:
        """Return automatic PumpSteer control mode."""
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        """Remain idle because shadow mode never operates heating hardware."""
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs) -> None:
        """Set room target and immediately request a shadow calculation."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        target = float(temperature)
        self._runtime.set_target_temperature(target)
        if self._entry.data.get(CONF_TARGET_TEMPERATURE) != target:
            self._hass.config_entries.async_update_entry(
                self._entry,
                data={
                    **self._entry.data,
                    CONF_TARGET_TEMPERATURE: target,
                },
            )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Reject modes other than AUTO until a bypass contract exists."""
        if hvac_mode != HVACMode.AUTO:
            raise ValueError("PumpSteer V3 alpha only supports AUTO")
