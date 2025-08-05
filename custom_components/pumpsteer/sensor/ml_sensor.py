# ml_sensor.py – Improved ML analysis sensor for PumpSteer

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from ..ml_adaptive import PumpSteerMLCollector
from ..utils import safe_float, get_state


class PumpSteerMLSensor(Entity):
    """Sensor that displays insights from the PumpSteer ML system."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._attr_name = "PumpSteer ML Analysis"
        self._attr_unique_id = f"{config_entry.entry_id}_ml_analysis"
        self._state = "initializing"
        self._attributes = {}
        self.ml = PumpSteerMLCollector(hass)

        self._attr_device_info = {
            "identifiers": {("pumpsteer", config_entry.entry_id)},
            "name": "PumpSteer",
            "manufacturer": "Custom",
            "model": "PumpSteer ML",
            "sw_version": "1.2.0"
        }

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

            autotune_on = self.hass.states.is_state("input_boolean.autotune_inertia", "on")
            integral = safe_float(get_state(self.hass, "input_number.integral_temp_error"))
            gain = safe_float(get_state(self.hass, "input_number.pumpsteer_integral_gain"))
            inertia = safe_float(get_state(self.hass, "input_number.house_inertia"))
            last_gain_adjust = get_state(self.hass, "input_text.last_gain_adjustment")

            success = perf.get("success_rate")
            if isinstance(success, (int, float)):
                self._state = f"{success:.0f}%"
            elif status.get("collecting_data"):
                self._state = "collecting"
            elif status.get("ml_status") == "ready":
                self._state = "ready"
            elif insights.get("sessions_collected", 0) == 0:
                self._state = "no data"
            else:
                self._state = "-"

            self._attributes = {
                "success_rate": round(success, 2) if isinstance(success, (int, float)) else None,
                "avg_heating_duration": perf.get("avg_heating_duration") or None,
                "most_used_aggressiveness": perf.get("most_used_aggressiveness") or None,
                "total_heating_sessions": perf.get("total_heating_sessions") or None,
                "recommendations": recs or "Still collecting data…",
                "auto_tune_active": autotune_on,
                "inertia": round(inertia, 3) if isinstance(inertia, (int, float)) else None,
                "integral_temp_error": round(integral, 2) if isinstance(integral, (int, float)) else 0,
                "integral_gain": round(gain, 3) if isinstance(gain, (int, float)) else 0,
                "last_gain_adjustment": last_gain_adjust if last_gain_adjust not in [None, "unknown"] else "-",
                "ml_status": status.get("ml_status") or "-",
                "collecting_data": status.get("collecting_data", False),
                "sessions_collected": status.get("sessions_collected", 0),
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
    ml_sensor = PumpSteerMLSensor(hass, config_entry)
    async_add_entities([ml_sensor], update_before_add=True)
