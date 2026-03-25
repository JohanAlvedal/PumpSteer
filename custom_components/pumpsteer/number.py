"""Number entities for PumpSteer."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreNumber
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import StateType

from .const import DOMAIN


@dataclass(frozen=True)
class PumpSteerNumberDescription:
    """Description for a PumpSteer number entity."""

    key: str
    name: str
    icon: str
    native_min_value: float
    native_max_value: float
    native_step: float
    native_unit_of_measurement: str | None = None
    mode: NumberMode = NumberMode.SLIDER
    default_value: float = 0.0


NUMBER_ENTITIES: tuple[PumpSteerNumberDescription, ...] = (
    PumpSteerNumberDescription(
        key="target_temperature",
        name="Target Temperature",
        icon="mdi:thermometer",
        native_min_value=16.0,
        native_max_value=27.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.SLIDER,
        default_value=21.0,
    ),
    PumpSteerNumberDescription(
        key="summer_threshold",
        name="Summer Mode Threshold",
        icon="mdi:weather-sunny",
        native_min_value=10.0,
        native_max_value=30.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.SLIDER,
        default_value=17.0,
    ),
    PumpSteerNumberDescription(
        key="aggressiveness",
        name="Saving Level",
        icon="mdi:lightning-bolt-circle",
        native_min_value=0.0,
        native_max_value=5.0,
        native_step=1.0,
        native_unit_of_measurement=None,
        mode=NumberMode.SLIDER,
        default_value=3.0,
    ),
    PumpSteerNumberDescription(
        key="house_inertia",
        name="House Thermal Mass",
        icon="mdi:home-thermometer",
        native_min_value=0.5,
        native_max_value=10.0,
        native_step=0.5,
        native_unit_of_measurement=None,
        mode=NumberMode.SLIDER,
        default_value=2.0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PumpSteer number entities."""
    async_add_entities(
        [PumpSteerNumberEntity(entry, description) for description in NUMBER_ENTITIES]
    )


class PumpSteerNumberEntity(RestoreNumber, NumberEntity):
    """PumpSteer number entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        description: PumpSteerNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_mode = description.mode
        self._attr_native_unit_of_measurement = (
            description.native_unit_of_measurement
        )
        self._attr_native_value = description.default_value

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PumpSteer",
            manufacturer="Johan Alvedal",
            model="PumpSteer",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None:
            self._attr_native_value = last_number_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return extra state attributes."""
        if self.entity_description.key == "aggressiveness":
            return {
                "description_0": "No price control, pure comfort",
                "description_1": "Very gentle, barely noticeable",
                "description_2": "Mild saving",
                "description_3": "Balanced (recommended)",
                "description_4": "Aggressive saving",
                "description_5": "Maximum saving, can get cold",
            }

        if self.entity_description.key == "house_inertia":
            return {
                "low_range": "0.5-2.0 lightweight house, reacts quickly",
                "mid_range": "2.0-4.0 typical house",
                "high_range": "4.0-10.0 heavy house, slow to heat/cool",
            }

        return {}
