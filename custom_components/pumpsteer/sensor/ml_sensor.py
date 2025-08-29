# ml_sensor.py – Improved ML analysis sensor for PumpSteer

import logging
import json
from pathlib import Path
from typing import Dict, Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.device_registry import DeviceInfo
import homeassistant.util.dt as dt_util

from ..ml_adaptive import PumpSteerMLCollector
from ..utils import safe_float, get_state

_LOGGER = logging.getLogger(__name__)


def _get_version() -> str:
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.json"
    try:
        with open(manifest_path) as manifest_file:
            return json.load(manifest_file).get("version", "1.3.4")
    except FileNotFoundError:
        return "1.3.4"


SW_VERSION = _get_version()

# Important ML-related entities - these are critical for PumpSteer control
ML_RELATED_ENTITIES = {
    # Core ML control entities
    "autotune_boolean": "input_boolean.autotune_inertia",  # Enable/disable auto-tuning
    "house_inertia": "input_number.house_inertia",  # House thermal inertia
    # Integral control entities (critical for temperature regulation)
    "integral_error": "input_number.integral_temp_error",  # Accumulated temperature error
    "integral_gain": "input_number.pumpsteer_integral_gain",  # Integral control gain
    # Status tracking
    "last_gain_adjustment": "input_text.last_gain_adjustment",  # Last automatic adjustment info
}


class PumpSteerMLSensor(Entity):
    """Sensor that displays insights from the PumpSteer ML system."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize ML sensor."""
        self.hass = hass
        self._attr_name = "PumpSteer ML Analysis"
        self._attr_unique_id = f"{config_entry.entry_id}_ml_analysis"
        self._state = "initializing"
        self._attributes = {}
        self.ml = None
        self._last_error = None

        self._attr_device_info = DeviceInfo(
            identifiers={("pumpsteer", config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="Custom",
            model="PumpSteer ML",
            sw_version=SW_VERSION,
        )

        # Initialize ML collector with error handling
        try:
            self.ml = PumpSteerMLCollector(hass)
            _LOGGER.debug("ML sensor: PumpSteerMLCollector initialized")
        except Exception as e:
            _LOGGER.error(f"ML sensor: Failed to initialize ML collector: {e}")
            self.ml = None
            self._last_error = f"Initialization failed: {e}"

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
        """Sensor is available if ML collector is working."""
        return self.ml is not None and self._state != STATE_UNAVAILABLE

    @property
    def icon(self) -> str:
        """Icon for ML sensor."""
        if self._state == "error":
            return "mdi:alert-circle"
        elif self._state == "collecting":
            return "mdi:database-search"
        elif isinstance(self._state, str) and self._state.endswith("%"):
            return "mdi:chart-line"
        else:
            return "mdi:brain"

    async def async_added_to_hass(self):
        """Load ML data when sensor is added."""
        if self.ml and hasattr(self.ml, "async_load_data"):
            try:
                await self.ml.async_load_data()
                _LOGGER.debug("ML sensor: Data loaded successfully")
            except Exception as e:
                _LOGGER.error(f"ML sensor: Failed to load data: {e}")
                self._last_error = f"Data loading failed: {e}"

    async def async_will_remove_from_hass(self) -> None:
        """Handle cleanup when entity is removed."""
        if self.ml and hasattr(self.ml, "async_shutdown"):
            try:
                await self.ml.async_shutdown()
            except Exception as e:
                _LOGGER.error(f"ML sensor: Error during shutdown: {e}")
        self.ml = None
        await super().async_will_remove_from_hass()

    def _get_control_system_data(self) -> Dict[str, Any]:
        """Get data from Home Assistant control system entities."""
        try:
            # Auto-tune status
            autotune_state = self.hass.states.get(
                ML_RELATED_ENTITIES["autotune_boolean"]
            )
            autotune_on = autotune_state.state == "on" if autotune_state else False

            # Get all critical control values
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

            _LOGGER.debug(
                f"ML sensor control data: autotune={autotune_on}, "
                f"inertia={house_inertia}, integral_gain={integral_gain}, "
                f"integral_error={integral_error}"
            )

            return {
                "autotune_active": autotune_on,
                "integral_error": integral_error,
                "integral_gain": integral_gain,
                "inertia": house_inertia,
                "last_gain_adjustment": last_adjustment,
            }
        except Exception as e:
            _LOGGER.warning(f"ML sensor: Error getting control system data: {e}")
            return {
                "autotune_active": False,
                "integral_error": 0.0,
                "integral_gain": 0.0,
                "inertia": None,
                "last_gain_adjustment": None,
            }

    def _determine_state(
        self, insights: Dict[str, Any], control_data: Dict[str, Any]
    ) -> str:
        """Determine sensor state based on ML insights and system status."""
        if not insights:
            return "no data"

        # Check ML status first
        status = insights.get("ml_status", {})
        if not isinstance(status, dict):
            status = {}

        if status.get("collecting_data"):
            return "collecting"

        # Try to show success rate if available
        perf = insights.get("performance", {})
        if isinstance(perf, dict):
            success = perf.get("success_rate")
            if isinstance(success, (int, float)) and 0 <= success <= 100:
                return f"{success:.0f}%"

        # Fallback states
        if status.get("ml_status") == "ready":
            return "ready"
        elif insights.get("sessions_collected", 0) == 0:
            return "no data"
        else:
            return "analyzing"

    def _build_attributes(
        self, insights: Dict[str, Any], control_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build comprehensive attributes dictionary."""
        # Safely extract performance data
        perf = (
            insights.get("performance", {})
            if isinstance(insights.get("performance"), dict)
            else {}
        )
        status = (
            insights.get("ml_status", {})
            if isinstance(insights.get("ml_status"), dict)
            else {}
        )
        recs = insights.get("recommendations", [])

        # Ensure recommendations is a list
        if not isinstance(recs, list):
            recs = []

        # Format recommendations
        recommendations_text = recs if recs else "Collecting data…"

        # Build attributes with safe access
        attributes = {
            # ML Performance
            "success_rate": (
                round(perf.get("success_rate"), 2)
                if isinstance(perf.get("success_rate"), (int, float))
                else None
            ),
            "avg_heating_duration": perf.get("avg_heating_duration"),
            "most_used_aggressiveness": perf.get("most_used_aggressiveness"),
            "total_heating_sessions": perf.get("total_heating_sessions") or 0,
            # Recommendations
            "recommendations": recommendations_text,
            # Control System Status
            "auto_tune_active": control_data.get("autotune_active", False),
            "inertia": (
                round(control_data["inertia"], 3)
                if isinstance(control_data.get("inertia"), (int, float))
                else None
            ),
            "integral_temp_error": round(control_data["integral_error"], 2),
            "integral_gain": round(control_data["integral_gain"], 3),
            "last_gain_adjustment": (
                control_data.get("last_gain_adjustment")
                if control_data.get("last_gain_adjustment") not in [None, "unknown", ""]
                else "-"
            ),
            # ML System Status
            "ml_status": status.get("ml_status", "unknown"),
            "collecting_data": status.get("collecting_data", False),
            "sessions_collected": status.get("sessions_collected", 0),
            # Meta
            "last_updated": dt_util.now().isoformat(),
            "last_error": self._last_error,
        }

        # Remove None values to keep attributes clean
        return {k: v for k, v in attributes.items() if v is not None}

    async def async_update(self):
        """Update ML sensor with comprehensive error handling."""
        if not self.ml:
            self._state = STATE_UNAVAILABLE
            self._attributes = {
                "error": "ML collector not available",
                "last_error": self._last_error,
                "last_updated": dt_util.now().isoformat(),
            }
            return

        try:
            # Get ML insights with validation
            insights = self.ml.get_learning_insights()
            if not isinstance(insights, dict):
                _LOGGER.warning(
                    "ML sensor: get_learning_insights() returned invalid data"
                )
                insights = {}

            # Get control system data
            control_data = self._get_control_system_data()

            # Determine state
            self._state = self._determine_state(insights, control_data)

            # Build attributes
            self._attributes = self._build_attributes(insights, control_data)

            # Clear error if update was successful
            if self._last_error:
                _LOGGER.info("ML sensor: Recovered from previous error")
                self._last_error = None

        except Exception as e:
            _LOGGER.error(f"ML sensor update failed: {e}", exc_info=True)
            self._state = "error"
            self._last_error = str(e)
            self._attributes = {
                "error": str(e),
                "last_error": self._last_error,
                "last_updated": dt_util.now().isoformat(),
                "error_count": self._attributes.get("error_count", 0) + 1,
            }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ML sensor."""
    ml_sensor = PumpSteerMLSensor(hass, config_entry)
    async_add_entities([ml_sensor], update_before_add=True)
