# ml_sensor.py – ML-analysens sensor

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from ..ml_adaptive import PumpSteerMLCollector

class PumpSteerMLSensor(Entity):
    """Sensor som visar insikter från PumpSteer ML-systemet."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._attr_name = "PumpSteer ML Analysis"
        self._attr_unique_id = f"{config_entry.entry_id}_ml_analysis"
        self._state = "initializing"
        self._attributes = {}

        self.ml = PumpSteerMLCollector(hass)

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_added_to_hass(self):
        await self.ml.async_load_data()

    async def async_update(self):
        try:
            insights = self.ml.get_learning_insights()
            perf = insights.get("performance", {})
            recs = insights.get("recommendations", [])
            status = insights.get("ml_status", {})

            self._state = status.get("ml_status", "ready")
            self._attributes = {
                "success_rate": perf.get("success_rate"),
                "avg_heating_duration": perf.get("avg_heating_duration"),
                "most_used_aggressiveness": perf.get("most_used_aggressiveness"),
                "total_heating_sessions": perf.get("total_heating_sessions"),
                "recommendations": recs,
                "auto_tune_active": self.hass.states.is_state("input_boolean.autotune_inertia", "on"),
                "last_updated": dt_util.now().isoformat()
            }

        except Exception as e:
            self._state = "error"
            self._attributes = {"error": str(e)}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Registrera endast ML-sensorn i denna modul om separat hantering önskas."""
    ml_sensor = PumpSteerMLSensor(hass, config_entry)
    async_add_entities([ml_sensor], update_before_add=True)
