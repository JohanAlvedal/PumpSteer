import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import STATE_UNAVAILABLE

from ..utils import get_version

_LOGGER = logging.getLogger(__name__)
SW_VERSION = get_version()

class HeatDemandSensor(Entity):
    """Sensor som automatiskt beräknar värme/kylbehov (-10 till +10) utifrån temperaturfel över tid."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry
        
        # Get entity IDs from config
        config = {**config_entry.data, **config_entry.options}
        self._indoor_temp_entity = config.get("indoor_temp_entity")
        self._target_temp_entity = config.get("target_temp_entity")
        
        self._state = 0
        self._temp_error_history = []
        self._history_length = 12
        self._name = "PumpSteer Heat Demand"
        self._attr_unique_id = f"{config_entry.entry_id}_heat_demand"
        
        self._attr_device_info = DeviceInfo(
            identifiers={("pumpsteer", config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="Custom",
            model="Heat Pump Controller",
            sw_version=SW_VERSION,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    @property
    def state(self) -> StateType:
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return "heat_demand (-10 to +10)"

    @property
    def icon(self) -> str:
        """Return icon based on heat demand state."""
        if self._state > 5:
            return "mdi:fire"
        elif self._state > 0:
            return "mdi:thermometer-plus"
        elif self._state < -5:
            return "mdi:snowflake"
        elif self._state < 0:
            return "mdi:thermometer-minus"
        else:
            return "mdi:thermometer"

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self._state != STATE_UNAVAILABLE

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "avg_error": round(self._calc_avg_error(), 2),
            "history": self._temp_error_history,
        }

    def _get_temperature(self, entity_id: str) -> float:
        try:
            state = self.hass.states.get(entity_id)
            return float(state.state) if state and state.state not in (None, "unknown", "unavailable") else None
        except Exception as e:
            _LOGGER.error(f"Error reading temperature from {entity_id}: {e}")
            return None

    def _calc_avg_error(self) -> float:
        if not self._temp_error_history:
            return 0.0
        return sum(self._temp_error_history[-self._history_length:]) / min(len(self._temp_error_history), self._history_length)

    async def async_update(self) -> None:
        """Update the heat demand sensor."""
        if not self._indoor_temp_entity or not self._target_temp_entity:
            _LOGGER.error("Heat demand sensor: Missing entity configuration")
            self._state = STATE_UNAVAILABLE
            return
            
        indoor_temp = self._get_temperature(self._indoor_temp_entity)
        target_temp = self._get_temperature(self._target_temp_entity)
        if indoor_temp is None or target_temp is None:
            _LOGGER.warning(f"Heat demand sensor: Unable to read temperatures (indoor: {indoor_temp}, target: {target_temp})")
            self._state = 0
            return

        temp_error = target_temp - indoor_temp
        self._temp_error_history.append(temp_error)
        # Begränsa historikens längd
        max_history = self._history_length * 4
        if len(self._temp_error_history) > max_history:
            self._temp_error_history = self._temp_error_history[-max_history:]

        avg_error = self._calc_avg_error()
        # Heat demand: -10 (kyla) till +10 (värme)
        heat_demand = max(-10, min(10, avg_error * 2))
        self._state = round(heat_demand, 1)
