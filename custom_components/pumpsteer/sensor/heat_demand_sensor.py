import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import StateType

_LOGGER = logging.getLogger(__name__)

class HeatDemandSensor(Entity):
    """Sensor som automatiskt beräknar värme/kylbehov (-10 till +10) utifrån temperaturfel över tid."""

    def __init__(self, hass: HomeAssistant, indoor_temp_entity: str, target_temp_entity: str, history_length: int = 12):
        self.hass = hass
        self._indoor_temp_entity = indoor_temp_entity
        self._target_temp_entity = target_temp_entity
        self._state = 0
        self._temp_error_history = []
        self._history_length = history_length
        self._name = "PumpSteer Heat Demand"

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> StateType:
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return "heat_demand (-10 to +10)"

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
        indoor_temp = self._get_temperature(self._indoor_temp_entity)
        target_temp = self._get_temperature(self._target_temp_entity)
        if indoor_temp is None or target_temp is None:
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
