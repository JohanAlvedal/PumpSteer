import logging
from typing import Dict, Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.device_registry import DeviceInfo
import homeassistant.util.dt as dt_util

from ..ml_adaptive import PumpSteerMLCollector
from ..utils import safe_float, get_state, get_version
from ..ml_settings import ML_MIN_SESSIONS_FOR_ANALYSIS

_LOGGER = logging.getLogger(__name__)

SW_VERSION = get_version()

# Related Home Assistant entities used for cross-reference
ML_RELATED_ENTITIES = {
    "autotune_boolean": "input_boolean.autotune_inertia",
    "house_inertia": "input_number.house_inertia",
    "integral_error": "input_number.integral_temp_error",
    "integral_gain": "input_number.pumpsteer_integral_gain",
    "last_gain_adjustment": "input_text.last_gain_adjustment",
}


class PumpSteerMLSensor(Entity):
    """Sensor that displays insights and learning results from PumpSteer ML"""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize ML sensor"""
        self.hass = hass
        self._attr_name = "PumpSteer ML Analysis"
        self._attr_unique_id = f"{config_entry.entry_id}_ml_analysis"
        self._state = "initializing"
        self._attributes: Dict[str, Any] = {}
        self.ml: PumpSteerMLCollector | None = None
        self._last_error: str | None = None

        self._attr_device_info = DeviceInfo(
            identifiers={("pumpsteer", config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="Custom",
            model="PumpSteer ML",
            sw_version=SW_VERSION,
        )

        self.ml = PumpSteerMLCollector(hass)
        _LOGGER.debug("ML sensor: PumpSteerMLCollector initialized successfully")

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

    @property
    def available(self) -> bool:
        return self.ml is not None and self._state != STATE_UNAVAILABLE

    @property
    def icon(self) -> str:
        """Dynamic icon"""
        if self._state == "error":
            return "mdi:alert-circle"
        if self._state == "collecting":
            return "mdi:database-search"
        if self._state == "learning":
            return "mdi:brain"
        if self._state == "ready":
            return "mdi:chart-line"
        return "mdi:brain"

    async def async_added_to_hass(self):
        """Load ML data on startup"""
        if self.ml and hasattr(self.ml, "async_load_data"):
            await self.ml.async_load_data()
            _LOGGER.debug("ML sensor: Data loaded successfully")

    async def async_will_remove_from_hass(self):
        """Clean up when entity is removed"""
        if self.ml and hasattr(self.ml, "async_shutdown"):
            await self.ml.async_shutdown()

        self.ml = None
        await super().async_will_remove_from_hass()

    def _get_control_system_data(self) -> Dict[str, Any]:
        """Fetch core control parameters from HA entities"""

        autotune_state = self.hass.states.get(ML_RELATED_ENTITIES["autotune_boolean"])
        autotune_on = autotune_state and autotune_state.state == "on"

        integral_error = (
            safe_float(get_state(self.hass, ML_RELATED_ENTITIES["integral_error"]))
            or 0.0
        )
        integral_gain = (
            safe_float(get_state(self.hass, ML_RELATED_ENTITIES["integral_gain"]))
            or 0.0
        )
        house_inertia = safe_float(
            get_state(self.hass, ML_RELATED_ENTITIES["house_inertia"])
        )
        last_adjustment = get_state(
            self.hass, ML_RELATED_ENTITIES["last_gain_adjustment"]
        )

        return {
            "autotune_active": autotune_on,
            "integral_error": integral_error,
            "integral_gain": integral_gain,
            "inertia": house_inertia,
            "last_gain_adjustment": last_adjustment,
        }

    def _determine_state(self, insights: Dict[str, Any]) -> str:
        """Decide what the main state string should be"""
        summary = insights.get("summary", {}) or {}
        total = summary.get("total_sessions", 0) or 0
        coeffs = summary.get("coefficients")

        # Too few sessions collected → still collecting data
        if total < ML_MIN_SESSIONS_FOR_ANALYSIS:
            return "collecting"

        # Enough sessions but model has not produced coefficients yet
        if not coeffs or (isinstance(coeffs, list) and len(coeffs) == 0):
            return "learning"

        # Model trained and coefficients exist → ready
        return "ready"

    def _build_attributes(
        self, insights: Dict[str, Any], control_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a clear and concise attribute dictionary"""
        summary = insights.get("summary", {})
        recs = insights.get("recommendations", [])

        attributes = {
            "total_sessions": summary.get("total_sessions"),
            "avg_duration": summary.get("avg_duration"),
            "avg_drift": summary.get("avg_drift"),
            "avg_inertia": summary.get("avg_inertia"),
            "avg_aggressiveness": summary.get("avg_aggressiveness"),
            "coefficients": summary.get("coefficients"),
            "recommendations": recs or ["Collecting data…"],
            "last_learning_update": summary.get("updated"),
            # control system info
            "auto_tune_active": control_data.get("autotune_active"),
            "inertia": control_data.get("inertia"),
            "integral_gain": control_data.get("integral_gain"),
            "integral_error": control_data.get("integral_error"),
            "last_gain_adjustment": control_data.get("last_gain_adjustment"),
            # meta
            "last_updated": dt_util.now().isoformat(),
            "last_error": self._last_error,
            "model_ready": bool(summary.get("coefficients")),
        }

        return {k: v for k, v in attributes.items() if v is not None}

    async def async_update(self):
        """Refresh ML information and update sensor attributes"""
        if not self.ml:
            self._state = STATE_UNAVAILABLE
            self._attributes = {
                "error": "ML collector not available",
                "last_error": self._last_error,
                "last_updated": dt_util.now().isoformat(),
            }
            return

        insights = {}

        summary = self.ml.get_learning_summary()
        recs = self.ml.get_recommendations()
        insights["summary"] = summary or {}
        insights["recommendations"] = recs or []

        control_data = self._get_control_system_data()

        # determine overall state
        self._state = self._determine_state(insights)
        self._attributes = self._build_attributes(insights, control_data)

        if self._last_error:
            _LOGGER.info("ML sensor: recovered from previous error")
            self._last_error = None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PumpSteer ML sensor entity"""
    ml_sensor = PumpSteerMLSensor(hass, config_entry)
    async_add_entities([ml_sensor], update_before_add=True)
