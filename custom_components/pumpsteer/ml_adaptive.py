# ml_adaptive.py - Improved but simple version

import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
import statistics

# Import HomeAssistant and dt_util for async execution and accurate timestamps
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)


class PumpSteerMLCollector:
    """
    Collects data for machine learning and provides basic analysis.
    Improved version with simple recommendations and trends.
    """
    # ml_adaptive.py - Improved version with separate ML settings

import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
import statistics

# Import HomeAssistant and dt_util for async execution and accurate timestamps
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

# Import all ML-specific constants from separate ML settings file
from .ml_settings import (
    ML_MODULE_VERSION,
    ML_DATA_FILE_PATH,
    ML_MAX_SAVED_SESSIONS,
    ML_MAX_SESSION_UPDATES,
    ML_TRIMMED_UPDATES,
    ML_DATA_VERSION,
    ML_MIN_SESSIONS_FOR_ANALYSIS,
    ML_MIN_SESSIONS_FOR_RECOMMENDATIONS,
    ML_MIN_SESSIONS_FOR_AUTOTUNE,
    ML_MIN_HEATING_SESSIONS,
    ML_ANALYSIS_RECENT_SESSIONS,
    ML_SUCCESS_DURATION_THRESHOLD,
    ML_SUCCESS_TEMP_DIFF_THRESHOLD,
    ML_FAILURE_DURATION_THRESHOLD,
    ML_MIN_DATA_POINTS,
    ML_LONG_DURATION_THRESHOLD,
    ML_SHORT_DURATION_THRESHOLD,
    ML_HIGH_INERTIA_THRESHOLD,
    ML_LOW_INERTIA_THRESHOLD,
    ML_HIGH_AGGRESSIVENESS_THRESHOLD,
    ML_LOW_AGGRESSIVENESS_THRESHOLD,
    ML_EXCELLENT_SUCCESS_RATE,
    ML_POOR_SUCCESS_RATE,
    ML_HIGH_SUCCESS_RATE_THRESHOLD,
    ML_INERTIA_ADJUSTMENT_STEP,
    ML_AGGRESSIVENESS_ADJUSTMENT_STEP,
    ML_AUTOTUNE_MIN_DAYS_BETWEEN,
    ML_DRIFT_HIGH_THRESHOLD,
    ML_DRIFT_LOW_THRESHOLD,
    ML_GAIN_ADJUSTMENT_STEP,
    ML_MAX_INTEGRAL_GAIN,
    ML_MIN_INTEGRAL_GAIN,
    ML_INERTIA_MAX_VALUE,
    ML_INERTIA_MIN_VALUE,
    ML_WARMING_TREND_THRESHOLD,
    ML_MIN_FORECAST_HOURS,
    ML_LEARN_PATIENCE_SESSIONS,
    ML_RECENT_SESSIONS_WINDOW,
    ML_NOTIFICATION_PREFIX,
    ML_AUTOTUNE_NOTIFICATION_ID,
    ML_RECOMMENDATION_NOTIFICATION_ID,
    ML_AUTOTUNE_BOOLEAN_ENTITY,
    ML_HOUSE_INERTIA_ENTITY,
    ML_INTEGRAL_GAIN_ENTITY,
    ML_DEBUG_MODE,
    ML_LOG_SESSION_DETAILS,
)

_LOGGER = logging.getLogger(__name__)


class PumpSteerMLCollector:
    """
    Collects data for machine learning and provides basic analysis.
    Improved version with separate ML settings and enhanced functionality.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        data_file_path: str = ML_DATA_FILE_PATH,
    ):
        """
        Initializes the ML data collector.

        Args:
            hass: HomeAssistant instance for asynchronous operations.
            data_file_path: Path to the JSON file for saving/loading data.
        """
        self.hass = hass
        self.data_file = data_file_path
        self.learning_sessions = []
        self.current_session = None
        self.last_inertia_adjustment = None
        self.last_gain_adjustment = None
        
        if ML_DEBUG_MODE:
            _LOGGER.setLevel(logging.DEBUG)
            
        _LOGGER.info(
            f"{ML_NOTIFICATION_PREFIX} Collector initialized (v{ML_MODULE_VERSION}) "
            f"- observation + analysis + auto-tune mode"
        )

    async def async_load_data(self) -> None:
        """Load saved data from file asynchronously."""
        try:
            await self.hass.async_add_executor_job(self._load_data_sync)
            _LOGGER.info(
                f"ML: Loaded {len(self.learning_sessions)} previous sessions from {self.data_file}"
            )
        except Exception as e:
            _LOGGER.error(f"ML: Error loading data asynchronously: {e}")
            self.learning_sessions = []

    def _load_data_sync(self) -> None:
        """Synchronous logic to load data, runs in executor."""
        if not Path(self.data_file).exists():
            _LOGGER.debug(
                f"ML: No existing data file found at {self.data_file}, starting fresh."
            )
            return

        with open(self.data_file, "r") as f:
            data = json.load(f)

        self.learning_sessions = data.get("sessions", [])
        
        # Log data version compatibility
        file_version = data.get("version", "unknown")
        if file_version != ML_DATA_VERSION:
            _LOGGER.warning(
                f"ML data file version mismatch: file={file_version}, expected={ML_DATA_VERSION}"
            )

    async def async_save_data(self) -> None:
        """Save collected data to file asynchronously."""
        try:
            await self.hass.async_add_executor_job(self._save_data_sync)
            if ML_DEBUG_MODE:
                _LOGGER.debug(
                    f"ML: Saved {len(self.learning_sessions)} sessions to {self.data_file}"
                )
        except Exception as e:
            _LOGGER.error(f"ML: Error saving data asynchronously: {e}")

    def _save_data_sync(self) -> None:
        """Synchronous logic to save data, runs in executor."""
        data = {
            "version": ML_DATA_VERSION,
            "ml_module_version": ML_MODULE_VERSION,
            "created": dt_util.now().isoformat(),
            "sessions": self.learning_sessions[-ML_MAX_SAVED_SESSIONS:],
            "session_count": len(self.learning_sessions),
        }
        Path(self.data_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, "w") as f:
            json.dump(data, f, indent=2)

    def start_session(self, initial_data: Dict[str, Any]) -> None:
        """Start a new learning session."""
        if self.current_session is not None:
            self.end_session("interrupted")

        self.current_session = {
            "start_time": dt_util.now().isoformat(),
            "initial": initial_data.copy(),
            "updates": [],
            "end_result": None,
        }

        if ML_LOG_SESSION_DETAILS:
            _LOGGER.debug(
                f"ML: Started learning session - Mode: {initial_data.get('mode', 'unknown')}"
            )

    def update_session(self, update_data: Dict[str, Any]) -> None:
        """Update the ongoing session with new data."""
        if self.current_session is None:
            return

        update_entry = {
            "timestamp": dt_util.now().isoformat(),
            "data": update_data.copy(),
        }

        self.current_session["updates"].append(update_entry)

        # Limit memory usage by trimming old updates
        if len(self.current_session["updates"]) > ML_MAX_SESSION_UPDATES:
            self.current_session["updates"] = self.current_session["updates"][-ML_TRIMMED_UPDATES:]

    def end_session(
        self, reason: str = "normal", final_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """End the ongoing session and save the result."""
        if self.current_session is None:
            return

        self.current_session["end_time"] = dt_util.now().isoformat()
        self.current_session["end_reason"] = reason
        self.current_session["end_result"] = final_data

        # Basic analysis
        session_summary = self._analyze_session(self.current_session)
        self.current_session["summary"] = session_summary

        self.learning_sessions.append(self.current_session)
        self.current_session = None

        # Save to file asynchronously
        self.hass.loop.create_task(self.async_save_data())

        if ML_LOG_SESSION_DETAILS:
            _LOGGER.debug(
                f"ML: Session ended - Reason: {reason}, "
                f"Duration: {session_summary.get('duration_minutes', 0):.1f}min"
            )

    def _analyze_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a finished session and extract lessons."""
        try:
            start_time = datetime.fromisoformat(session["start_time"])
            end_time = datetime.fromisoformat(session["end_time"])
            duration_minutes = (end_time - start_time).total_seconds() / 60

            initial = session.get("initial", {})
            updates = session.get("updates", [])

            # Basic analysis
            summary = {
                "duration_minutes": round(duration_minutes, 1),
                "mode": initial.get("mode", "unknown"),
                "aggressiveness": initial.get("aggressiveness", 0),
                "inertia": initial.get("inertia", 1.0),
                "update_count": len(updates),
                "start_temp_diff": initial.get("indoor_temp", 0)
                                 - initial.get("target_temp", 0),
            }

            # Classify session success using ML settings constants
            if (
                duration_minutes < ML_SUCCESS_DURATION_THRESHOLD and
                abs(summary["start_temp_diff"]) > ML_SUCCESS_TEMP_DIFF_THRESHOLD
            ):
                summary["success"] = True
            elif duration_minutes > ML_FAILURE_DURATION_THRESHOLD:
                summary["success"] = False
            else:
                summary["success"] = None

            return summary

        except Exception as e:
            _LOGGER.error(f"ML: Error analyzing session: {e}")
            return {"duration_minutes": 0, "success": None, "mode": "error"}

    def get_status(self) -> Dict[str, Any]:
        """Get current status for the ML system."""
        return {
            "collecting_data": True,
            "making_recommendations": len(self.learning_sessions) >= ML_MIN_SESSIONS_FOR_RECOMMENDATIONS,
            "sessions_collected": len(self.learning_sessions),
            "current_session_active": self.current_session is not None,
            "data_file": self.data_file,
            "ready_for_insights": len(self.learning_sessions) >= ML_MIN_SESSIONS_FOR_RECOMMENDATIONS,
            "ml_version": ML_MODULE_VERSION,
            "debug_mode": ML_DEBUG_MODE,
        }

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary based on collected sessions."""
        if len(self.learning_sessions) < ML_MIN_SESSIONS_FOR_ANALYSIS:
            return {
                "status": "insufficient_data",
                "message": f"Need at least {ML_MIN_SESSIONS_FOR_ANALYSIS} sessions for analysis. Currently have {len(self.learning_sessions)}.",
            }

        try:
            # Analyze heating sessions only
            heating_sessions = [
                s
                for s in self.learning_sessions
                if s.get("summary", {}).get("mode") == "heating"
            ]

            if not heating_sessions:
                return {
                    "status": "no_heating_data",
                    "message": "No heating sessions to analyze yet.",
                }

            # Calculate statistics
            durations = [
                s["summary"]["duration_minutes"]
                for s in heating_sessions
                if s.get("summary", {}).get("duration_minutes", 0) > 0
            ]

            aggressiveness_values = [
                s["summary"]["aggressiveness"]
                for s in heating_sessions
                if s.get("summary", {}).get("aggressiveness") is not None
            ]

            successful_sessions = [
                s
                for s in heating_sessions
                if s.get("summary", {}).get("success") is True
            ]

            # Compile results
            summary = {
                "status": "analyzing",
                "total_heating_sessions": len(heating_sessions),
                "avg_heating_duration": (
                    round(statistics.mean(durations), 1) if durations else 0
                ),
                "success_rate": round(
                    len(successful_sessions) / len(heating_sessions) * 100, 1
                ),
                "most_used_aggressiveness": (
                    round(statistics.mode(aggressiveness_values), 1)
                    if aggressiveness_values
                    else 0
                ),
                "sessions_analyzed": len(self.learning_sessions),
            }

            return summary

        except Exception as e:
            _LOGGER.error(f"ML: Error in performance summary: {e}")
            return {"status": "error", "message": str(e)}

    def get_recommendations(self) -> List[str]:
        """Generate recommendations based on collected data using ML settings."""
        performance = self.get_performance_summary()

        if performance.get("status") != "analyzing":
            return ["Still collecting data to provide recommendations..."]

        recommendations = []

        try:
            # Analyze sessions to find patterns
            heating_sessions = [
                s
                for s in self.learning_sessions
                if s.get("summary", {}).get("mode") == "heating"
            ]

            if not heating_sessions:
                return ["No heating sessions to analyze yet."]

            # Gather data for analysis
            avg_duration = performance.get("avg_heating_duration", 0)
            success_rate = performance.get("success_rate", 0)
            most_used_agg = performance.get("most_used_aggressiveness", 3)

            # Analyze recent inertia patterns
            inertia_values = [
                s["summary"].get("inertia", 1.0) 
                for s in heating_sessions[-ML_ANALYSIS_RECENT_SESSIONS:]
            ]
            avg_inertia = statistics.mean(inertia_values) if inertia_values else 1.0

            # AGGRESSIVENESS recommendations using ML settings
            if most_used_agg == 0:
                recommendations.append(
                    "Aggressiveness 0: No money-saving logic active. System works as regular thermostat."
                )
            elif most_used_agg >= ML_HIGH_AGGRESSIVENESS_THRESHOLD and success_rate < ML_HIGH_SUCCESS_RATE_THRESHOLD:
                new_agg = most_used_agg - ML_AGGRESSIVENESS_ADJUSTMENT_STEP
                recommendations.append(
                    f"Aggressiveness {most_used_agg} gives high savings but low comfort "
                    f"({success_rate:.1f}% success). Consider decreasing to {new_agg} for better balance."
                )
            elif most_used_agg <= ML_LOW_AGGRESSIVENESS_THRESHOLD and avg_duration < 45:
                new_agg = most_used_agg + ML_AGGRESSIVENESS_ADJUSTMENT_STEP
                recommendations.append(
                    f"Aggressiveness {most_used_agg} prioritizes comfort. You can increase to "
                    f"{new_agg} for more savings if comfort is acceptable."
                )

            # HOUSE_INERTIA recommendations using ML settings
            if avg_duration > ML_LONG_DURATION_THRESHOLD and avg_inertia < ML_LOW_INERTIA_THRESHOLD:
                new_inertia = avg_inertia + ML_INERTIA_ADJUSTMENT_STEP
                recommendations.append(
                    f"Heating takes long ({avg_duration:.1f}min) with house_inertia {avg_inertia:.1f}. "
                    f"Your house may respond slowly – try increasing to {new_inertia:.1f}."
                )
            elif avg_duration < ML_SHORT_DURATION_THRESHOLD and avg_inertia > ML_HIGH_INERTIA_THRESHOLD:
                new_inertia = avg_inertia - ML_INERTIA_ADJUSTMENT_STEP
                recommendations.append(
                    f"Very short heating sessions ({avg_duration:.1f}min) with house_inertia {avg_inertia:.1f}. "
                    f"Your house responds quickly – consider decreasing to {new_inertia:.1f}."
                )

            # SUCCESS RATE analysis using ML settings
            if success_rate > ML_EXCELLENT_SUCCESS_RATE:
                recommendations.append(
                    f"Excellent balance between savings and comfort ({success_rate:.1f}% success)! "
                    f"Current settings work well."
                )
            elif success_rate < ML_POOR_SUCCESS_RATE:
                recommendations.append(
                    f"Low success rate ({success_rate:.1f}%). Adjust either aggressiveness "
                    f"(savings/comfort balance) or house_inertia (thermal response)."
                )

            # Learning patience advice
            if len(self.learning_sessions) < ML_LEARN_PATIENCE_SESSIONS:
                recommendations.append(
                    f"System is still learning. Wait before major changes until "
                    f"{ML_LEARN_PATIENCE_SESSIONS}+ sessions are collected."
                )

            # Default advice
            if len(recommendations) == 0:
                recommendations.append(
                    "Reminder: Aggressiveness (0-5) = savings vs comfort. "
                    "House_inertia (0-5) = thermal response speed."
                )

            return recommendations

        except Exception as e:
            _LOGGER.error(f"ML: Error generating recommendations: {e}")
            return ["Error generating recommendations."]

    def get_learning_insights(self) -> Dict[str, Any]:
        """Combine all ML information and check auto-tune possibilities."""
        try:
            status = self.get_status()
            performance = self.get_performance_summary()
            recommendations = self.get_recommendations()

            # Check if auto-tune should run
            if len(self.learning_sessions) >= ML_MIN_SESSIONS_FOR_AUTOTUNE:
                auto_tune_result = self._check_auto_tune_inertia()
                if auto_tune_result:
                    recommendations.extend(auto_tune_result.get("notifications", []))

                gain_tune_result = self._check_auto_tune_integral_gain()
                if gain_tune_result:
                    recommendations.extend(gain_tune_result.get("notifications", []))

            return {
                "ml_status": status,
                "performance": performance,
                "recommendations": recommendations,
                "last_updated": dt_util.now().isoformat(),
                "ml_version": ML_MODULE_VERSION,
            }

        except Exception as e:
            _LOGGER.error(f"ML: Error getting learning insights: {e}")
            return {"error": str(e), "ml_status": self.get_status()}

    def _check_auto_tune_integral_gain(self) -> Optional[Dict[str, Any]]:
        """Auto-tune integral gain based on session history."""
        try:
            auto_tune_state = self.hass.states.get(ML_AUTOTUNE_BOOLEAN_ENTITY)
            auto_tune_enabled = auto_tune_state and auto_tune_state.state == "on"

            gain_entity = self.hass.states.get(ML_INTEGRAL_GAIN_ENTITY)
            if not gain_entity:
                return None

            current_gain = float(gain_entity.state)
            heating_sessions = [
                s
                for s in self.learning_sessions[-ML_RECENT_SESSIONS_WINDOW:]
                if s.get("summary", {}).get("mode") == "heating"
            ]

            if len(heating_sessions) < ML_MIN_HEATING_SESSIONS:
                return None

            # Avoid too frequent adjustments
            if (
                self.last_gain_adjustment
                and (
                    dt_util.now() - datetime.fromisoformat(self.last_gain_adjustment)
                ).days < ML_AUTOTUNE_MIN_DAYS_BETWEEN
            ):
                return None

            # Analyze temperature drift patterns
            errors = []
            for s in heating_sessions:
                updates = s.get("updates", [])
                if not updates:
                    continue
                start = updates[0]["data"]
                end = updates[-1]["data"]
                error_start = start.get("target_temp", 0) - start.get("indoor_temp", 0)
                error_end = end.get("target_temp", 0) - end.get("indoor_temp", 0)
                errors.append(error_end - error_start)

            if not errors:
                return None

            avg_drift = statistics.mean(errors)
            suggested_gain = current_gain
            reason = ""
            action_needed = False

            # Check if gain adjustment is needed using ML settings
            if avg_drift > ML_DRIFT_HIGH_THRESHOLD and current_gain < ML_MAX_INTEGRAL_GAIN:
                suggested_gain = min(current_gain + ML_GAIN_ADJUSTMENT_STEP, ML_MAX_INTEGRAL_GAIN)
                reason = f"System accumulates temperature error over time (drift={avg_drift:.2f})."
                action_needed = True
            elif avg_drift < ML_DRIFT_LOW_THRESHOLD and current_gain > ML_MIN_INTEGRAL_GAIN:
                suggested_gain = max(current_gain - ML_GAIN_ADJUSTMENT_STEP, ML_MIN_INTEGRAL_GAIN)
                reason = f"System overshoots target temperature (drift={avg_drift:.2f})."
                action_needed = True

            if not action_needed:
                return None

            notifications = []

            if auto_tune_enabled:
                try:
                    self.hass.services.call(
                        "input_number",
                        "set_value",
                        {
                            "entity_id": ML_INTEGRAL_GAIN_ENTITY,
                            "value": round(suggested_gain, 3),
                        },
                    )
                    msg = f"{ML_NOTIFICATION_PREFIX}: Adjusted integral_gain {current_gain} → {suggested_gain:.3f}. {reason}"
                    self.hass.services.call(
                        "persistent_notification",
                        "create",
                        {
                            "title": f"{ML_NOTIFICATION_PREFIX} Auto-Tune (Gain)",
                            "message": msg,
                            "notification_id": f"{ML_AUTOTUNE_NOTIFICATION_ID}_gain",
                        },
                    )
                    notifications.append(
                        f"✅ AUTO-ADJUSTED: integral_gain {current_gain} → {suggested_gain:.3f}"
                    )
                    _LOGGER.info(msg)
                    self.last_gain_adjustment = dt_util.now().isoformat()
                except Exception as e:
                    _LOGGER.error(f"Auto-tune (gain) failed: {e}")
                    notifications.append(f"❌ Gain auto-tune failed: {e}")
            else:
                tip_msg = f"💡 TIP: Consider changing integral_gain {current_gain} → {suggested_gain:.3f}. {reason}"
                self.hass.services.call(
                    "persistent_notification",
                    "create",
                    {
                        "title": f"{ML_NOTIFICATION_PREFIX} Recommendation (Gain)",
                        "message": tip_msg,
                        "notification_id": f"{ML_RECOMMENDATION_NOTIFICATION_ID}_gain",
                    },
                )
                notifications.append(
                    f"💡 RECOMMENDATION: integral_gain {current_gain} → {suggested_gain:.3f} ({reason})"
                )

            return {
                "action": "auto_tune" if auto_tune_enabled else "recommendation",
                "old_value": current_gain,
                "new_value": suggested_gain,
                "reason": reason,
                "notifications": notifications,
            }

        except Exception as e:
            _LOGGER.error(f"Error in gain auto-tune check: {e}")
            return None

    def _check_auto_tune_inertia(self) -> Optional[Dict[str, Any]]:
        """Auto-tune house inertia based on session history."""
        try:
            auto_tune_state = self.hass.states.get(ML_AUTOTUNE_BOOLEAN_ENTITY)
            auto_tune_enabled = auto_tune_state and auto_tune_state.state == "on"

            inertia_entity = self.hass.states.get(ML_HOUSE_INERTIA_ENTITY)
            if not inertia_entity:
                return None

            current_inertia = float(inertia_entity.state)
            heating_sessions = [
                s
                for s in self.learning_sessions[-ML_RECENT_SESSIONS_WINDOW:]
                if s.get("summary", {}).get("mode") == "heating"
            ]

            if len(heating_sessions) < ML_MIN_HEATING_SESSIONS:
                return None

            # Avoid too frequent adjustments
            if (
                self.last_inertia_adjustment
                and (
                    dt_util.now() - datetime.fromisoformat(self.last_inertia_adjustment)
                ).days < ML_AUTOTUNE_MIN_DAYS_BETWEEN
            ):
                return None

            # Analyze recent performance patterns
            durations = [
                s["summary"]["duration_minutes"]
                for s in heating_sessions
                if s.get("summary", {}).get("duration_minutes", 0) > 0
            ]

            if not durations:
                return None

            avg_duration = statistics.mean(durations)
            suggested_inertia = current_inertia
            reason = ""
            action_needed = False

            # Check if inertia adjustment is needed using ML settings
            if avg_duration > ML_LONG_DURATION_THRESHOLD and current_inertia < ML_INERTIA_MAX_VALUE:
                suggested_inertia = min(current_inertia + ML_INERTIA_ADJUSTMENT_STEP, ML_INERTIA_MAX_VALUE)
                reason = f"Heating sessions are long ({avg_duration:.1f}min avg). House may respond slowly."
                action_needed = True
            elif avg_duration < ML_SHORT_DURATION_THRESHOLD and current_inertia > ML_INERTIA_MIN_VALUE:
                suggested_inertia = max(current_inertia - ML_INERTIA_ADJUSTMENT_STEP, ML_INERTIA_MIN_VALUE)
                reason = f"Heating sessions are short ({avg_duration:.1f}min avg). House responds quickly."
                action_needed = True

            if not action_needed:
                return None

            notifications = []

            if auto_tune_enabled:
                try:
                    self.hass.services.call(
                        "input_number",
                        "set_value",
                        {
                            "entity_id": ML_HOUSE_INERTIA_ENTITY,
                            "value": round(suggested_inertia, 1),
                        },
                    )
                    msg = f"{ML_NOTIFICATION_PREFIX}: Adjusted house_inertia {current_inertia} → {suggested_inertia:.1f}. {reason}"
                    self.hass.services.call(
                        "persistent_notification",
                        "create",
                        {
                            "title": f"{ML_NOTIFICATION_PREFIX} Auto-Tune (Inertia)",
                            "message": msg,
                            "notification_id": f"{ML_AUTOTUNE_NOTIFICATION_ID}_inertia",
                        },
                    )
                    notifications.append(
                        f"✅ AUTO-ADJUSTED: house_inertia {current_inertia} → {suggested_inertia:.1f}"
                    )
                    _LOGGER.info(msg)
                    self.last_inertia_adjustment = dt_util.now().isoformat()
                except Exception as e:
                    _LOGGER.error(f"Auto-tune (inertia) failed: {e}")
                    notifications.append(f"❌ Inertia auto-tune failed: {e}")
            else:
                tip_msg = f"💡 TIP: Consider changing house_inertia {current_inertia} → {suggested_inertia:.1f}. {reason}"
                self.hass.services.call(
                    "persistent_notification",
                    "create",
                    {
                        "title": f"{ML_NOTIFICATION_PREFIX} Recommendation (Inertia)",
                        "message": tip_msg,
                        "notification_id": f"{ML_RECOMMENDATION_NOTIFICATION_ID}_inertia",
                    },
                )
                notifications.append(
                    f"💡 RECOMMENDATION: house_inertia {current_inertia} → {suggested_inertia:.1f} ({reason})"
                )

            return {
                "action": "auto_tune" if auto_tune_enabled else "recommendation",
                "old_value": current_inertia,
                "new_value": suggested_inertia,
                "reason": reason,
                "notifications": notifications,
            }

        except Exception as e:
            _LOGGER.error(f"Error in inertia auto-tune check: {e}")
            return None
    def __init__(
        self,
        hass: HomeAssistant,
        data_file_path: str = "/config/pumpsteer_ml_data.json",
    ):
        """
        Initializes the ML data collector.

        Args:
            hass: HomeAssistant instance for asynchronous operations.
            data_file_path: Path to the JSON file for saving/loading data.
        """
        self.hass = hass
        self.data_file = data_file_path
        self.learning_sessions = []
        self.current_session = None
        self.last_inertia_adjustment = None  # Track last adjustment
        self.last_gain_adjustment = None  # Track last gain adjustment
        _LOGGER.info(
            "PumpSteer Enhanced ML Collector initialized (observation + analysis + auto-tune mode)"
        )

    async def async_load_data(self) -> None:
        """Load saved data from file asynchronously."""
        try:
            await self.hass.async_add_executor_job(self._load_data_sync)
            _LOGGER.info(
                f"ML: Loaded {len(self.learning_sessions)} previous sessions from {self.data_file}"
            )
        except Exception as e:
            _LOGGER.error(f"ML: Error loading data asynchronously: {e}")
            self.learning_sessions = []

    def _load_data_sync(self) -> None:
        """Synchronous logic to load data, runs in executor."""
        if not Path(self.data_file).exists():
            _LOGGER.debug(
                f"ML: No existing data file found at {self.data_file}, starting fresh."
            )
            return

        with open(self.data_file, "r") as f:
            data = json.load(f)

        self.learning_sessions = data.get("sessions", [])

    async def async_save_data(self) -> None:
        """Save collected data to file asynchronously."""
        try:
            await self.hass.async_add_executor_job(self._save_data_sync)
            _LOGGER.debug(
                f"ML: Saved {len(self.learning_sessions)} sessions to {self.data_file}"
            )
        except Exception as e:
            _LOGGER.error(f"ML: Error saving data asynchronously: {e}")

    def _save_data_sync(self) -> None:
        """Synchronous logic to save data, runs in executor."""
        data = {
            "version": "1.0",
            "created": dt_util.now().isoformat(),
            "sessions": self.learning_sessions[
                -100:
            ],  # Save only the last 100 sessions
            "session_count": len(self.learning_sessions),
        }
        Path(self.data_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, "w") as f:
            json.dump(data, f, indent=2)

    def start_session(self, initial_data: Dict[str, Any]) -> None:
        """Start a new learning session."""
        if self.current_session is not None:
            self.end_session("interrupted")

        self.current_session = {
            "start_time": dt_util.now().isoformat(),
            "initial": initial_data.copy(),
            "updates": [],
            "end_result": None,
        }

        _LOGGER.debug(
            f"ML: Started learning session - Mode: {initial_data.get('mode', 'unknown')}"
        )

    def update_session(self, update_data: Dict[str, Any]) -> None:
        """Update the ongoing session with new data."""
        if self.current_session is None:
            return

        update_entry = {
            "timestamp": dt_util.now().isoformat(),
            "data": update_data.copy(),
        }

        self.current_session["updates"].append(update_entry)

        if len(self.current_session["updates"]) > 100:
            self.current_session["updates"] = self.current_session["updates"][-50:]

    def end_session(
        self, reason: str = "normal", final_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """End the ongoing session and save the result."""
        if self.current_session is None:
            return

        self.current_session["end_time"] = dt_util.now().isoformat()
        self.current_session["end_reason"] = reason
        self.current_session["end_result"] = final_data

        # Basic analysis
        session_summary = self._analyze_session(self.current_session)
        self.current_session["summary"] = session_summary

        self.learning_sessions.append(self.current_session)
        self.current_session = None

        # Save to file asynchronously
        self.hass.loop.create_task(self.async_save_data())

        _LOGGER.debug(
            f"ML: Session ended - Reason: {reason}, Duration: {session_summary.get('duration_minutes', 0):.1f}min"
        )

    def _analyze_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a finished session and extract lessons."""
        try:
            start_time = datetime.fromisoformat(session["start_time"])
            end_time = datetime.fromisoformat(session["end_time"])
            duration_minutes = (end_time - start_time).total_seconds() / 60

            initial = session.get("initial", {})
            updates = session.get("updates", [])

            # Basic analysis
            summary = {
                "duration_minutes": round(duration_minutes, 1),
                "mode": initial.get("mode", "unknown"),
                "aggressiveness": initial.get("aggressiveness", 0),
                "inertia": initial.get("inertia", 1.0),
                "update_count": len(updates),
                "start_temp_diff": initial.get("indoor_temp", 0)
                                 - initial.get("target_temp", 0),
            }

            # Classify session as successful or not
            # Under 2h for significant temperature difference
            # Over 3h indicates a problem
            if (
                duration_minutes < 120 and
                abs(summary["start_temp_diff"]) > 0.3
            ):
                summary["success"] = True
            elif duration_minutes > 180:
                summary["success"] = False
            else:
                summary["success"] = None

            return summary

        except Exception as e:
            _LOGGER.error(f"ML: Error analyzing session: {e}")
            return {"duration_minutes": 0, "success": None, "mode": "error"}

    def get_status(self) -> Dict[str, Any]:
        """Get current status for the ML system."""
        return {
            "collecting_data": True,
            "making_recommendations": len(self.learning_sessions) >= 5,
            "sessions_collected": len(self.learning_sessions),
            "current_session_active": self.current_session is not None,
            "data_file": self.data_file,
            "ready_for_insights": len(self.learning_sessions) >= 5,
        }

    # === NEW IMPROVED FUNCTIONS ===

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary based on collected sessions."""
        if len(self.learning_sessions) < 3:
            return {
                "status": "insufficient_data",
                "message": f"Need at least 3 sessions for analysis. Currently have {len(self.learning_sessions)}.",
            }

        try:
            # Analyze all sessions
            heating_sessions = [
                s
                for s in self.learning_sessions
                if s.get("summary", {}).get("mode") == "heating"
            ]

            if not heating_sessions:
                return {
                    "status": "no_heating_data",
                    "message": "No heating sessions to analyze yet.",
                }

            # Calculate statistics
            durations = [
                s["summary"]["duration_minutes"]
                for s in heating_sessions
                if s.get("summary", {}).get("duration_minutes", 0) > 0
            ]

            aggressiveness_values = [
                s["summary"]["aggressiveness"]
                for s in heating_sessions
                if s.get("summary", {}).get("aggressiveness") is not None
            ]

            successful_sessions = [
                s
                for s in heating_sessions
                if s.get("summary", {}).get("success") is True
            ]

            # Compile results
            summary = {
                "status": "analyzing",
                "total_heating_sessions": len(heating_sessions),
                "avg_heating_duration": (
                    round(statistics.mean(durations), 1) if durations else 0
                ),
                "success_rate": round(
                    len(successful_sessions) / len(heating_sessions) * 100, 1
                ),
                "most_used_aggressiveness": (
                    round(statistics.mode(aggressiveness_values), 1)
                    if aggressiveness_values
                    else 0
                ),
                "sessions_analyzed": len(self.learning_sessions),
            }

            return summary

        except Exception as e:
            _LOGGER.error(f"ML: Error in performance summary: {e}")
            return {"status": "error", "message": str(e)}

    def get_recommendations(self) -> List[str]:
        """Generate simple recommendations based on collected data according to correct design philosophy."""
        performance = self.get_performance_summary()

        if performance.get("status") != "analyzing":
            return ["Still collecting data to provide recommendations..."]

        recommendations = []

        try:
            # Analyze sessions to find patterns
            heating_sessions = [
                s
                for s in self.learning_sessions
                if s.get("summary", {}).get("mode") == "heating"
            ]

            if not heating_sessions:
                return ["No heating sessions to analyze yet."]

            # Gather data for analysis
            avg_duration = performance.get("avg_heating_duration", 0)
            success_rate = performance.get("success_rate", 0)
            most_used_agg = performance.get("most_used_aggressiveness", 3)

            # Analyze inertia vs duration patterns
            inertia_values = [
                s["summary"].get("inertia", 1.0) for s in heating_sessions[-10:]
            ]
            avg_inertia = statistics.mean(inertia_values) if inertia_values else 1.0

            # AGGRESSIVENESS recommendations (money-saving tool 0-5)
            if most_used_agg == 0:
                recommendations.append(
                    "Aggressiveness 0: No money-saving logic active. The system works as a regular thermostat."
                )
            elif most_used_agg >= 4 and success_rate < 70:
                recommendations.append(
                    f"Aggressiveness {most_used_agg} gives high savings but low comfort ({success_rate:.1f}% success). Consider decreasing to {most_used_agg - 1} for better balance."
                )
            elif most_used_agg <= 2 and avg_duration < 45:
                recommendations.append(
                    f"Aggressiveness {most_used_agg} prioritizes comfort. You can increase to {most_used_agg + 1} for more savings if comfort is acceptable."
                )

            # HOUSE_INERTIA recommendations (house inertia 0-5)
            if avg_duration > 120 and avg_inertia < 2.0:
                recommendations.append(
                    f"Heating takes a long time ({avg_duration:.1f}min) with house_inertia {avg_inertia:.1f}. Your house may be slower – try increasing house_inertia to {avg_inertia + 0.5:.1f}."
                )
            elif avg_duration < 20 and avg_inertia > 2.0:
                recommendations.append(
                    f"Very short heating sessions ({avg_duration:.1f}min) with house_inertia {avg_inertia:.1f}. Your house responds quickly – consider decreasing house_inertia to {avg_inertia - 0.5:.1f}."
                )

            # COMBINATION analysis (aggressiveness + inertia)
            if most_used_agg >= 4 and avg_inertia <= 1.0:
                recommendations.append(
                    "High aggressiveness (4-5) + low house_inertia (0-1): Risk of temperature fluctuations in a fast-reacting house with high savings."
                )
            elif most_used_agg <= 1 and avg_inertia >= 4.0:
                recommendations.append(
                    "Low aggressiveness (0-1) + high house_inertia (4-5): Stable but more expensive in a slow-reacting house with comfort priority."
                )

            # SUCCESS RATE analysis
            if success_rate > 85:
                recommendations.append(
                    f"Excellent balance between savings and comfort ({success_rate:.1f}% success)! Current settings work well."
                )
            elif success_rate < 60:
                recommendations.append(
                    f"Low success rate ({success_rate:.1f}%). Adjust either aggressiveness (savings/comfort balance) or house_inertia (house's inertia)."
                )

            # General advice
            if len(self.learning_sessions) < 10:
                recommendations.append(
                    "The system is still learning. Wait before making major changes until 10+ sessions are collected."
                )

            # DESIGN PHILOSOPHY reminder
            if len(recommendations) == 0:
                recommendations.append(
                    "Reminder: Aggressiveness (0-5) = savings vs comfort. House_inertia (0-5) = the house's thermal inertia."
                )

            return recommendations

        except Exception as e:
            _LOGGER.error(f"ML: Error generating recommendations: {e}")
            return ["Error generating recommendations."]

    def get_learning_insights(self) -> Dict[str, Any]:
        """Combine all information + check auto-tune possibilities."""
        try:
            status = self.get_status()
            performance = self.get_performance_summary()
            recommendations = self.get_recommendations()

            # Check if auto-tune should run
            if len(self.learning_sessions) >= 5:  # At least 5 sessions for auto-tune
                auto_tune_result = self._check_auto_tune_inertia()
                if auto_tune_result:
                    recommendations.extend(auto_tune_result.get("notifications", []))

                gain_tune_result = self._check_auto_tune_integral_gain()
                if gain_tune_result:
                    recommendations.extend(gain_tune_result.get("notifications", []))

            return {
                "ml_status": status,
                "performance": performance,
                "recommendations": recommendations,
                "last_updated": dt_util.now().isoformat(),
            }

        except Exception as e:
            _LOGGER.error(f"ML: Error getting learning insights: {e}")
            return {"error": str(e), "ml_status": self.get_status()}

    def _check_auto_tune_integral_gain(self) -> Optional[Dict[str, Any]]:
        """Auto-tune of integral gain based on history."""
        try:
            auto_tune_state = self.hass.states.get("input_boolean.autotune_inertia")
            auto_tune_enabled = auto_tune_state and auto_tune_state.state == "on"

            gain_entity = self.hass.states.get("input_number.pumpsteer_integral_gain")
            if not gain_entity:
                return None

            current_gain = float(gain_entity.state)
            heating_sessions = [
                s
                for s in self.learning_sessions[-10:]
                if s.get("summary", {}).get("mode") == "heating"
            ]

            if len(heating_sessions) < 3:
                return None

            # Avoid too frequent adjustments (max every 2 days)
            if (
                self.last_gain_adjustment
                and (
                    dt_util.now() - datetime.fromisoformat(self.last_gain_adjustment)
                ).days <
                2
            ):
                return None

            errors = []
            for s in heating_sessions:
                updates = s.get("updates", [])
                if not updates:
                    continue
                start = updates[0]["data"]
                end = updates[-1]["data"]
                error_start = start.get("target_temp", 0) - start.get("indoor_temp", 0)
                error_end = end.get("target_temp", 0) - end.get("indoor_temp", 0)
                errors.append(error_end - error_start)

            if not errors:
                return None

            avg_drift = statistics.mean(errors)

            suggested_gain = current_gain
            reason = ""
            action_needed = False

            if avg_drift > 0.3 and current_gain < 1.0:
                suggested_gain = min(current_gain + 0.05, 1.0)
                reason = (
                    f"The system accumulates temperature error over time (drift={avg_drift:.2f})."
                )
                action_needed = True
            elif avg_drift < -0.3 and current_gain > 0.01:
                suggested_gain = max(current_gain - 0.05, 0.0)
                reason = f"The system overshoots (drift={avg_drift:.2f})."
                action_needed = True

            if not action_needed:
                return None

            notifications = []

            if auto_tune_enabled:
                try:
                    self.hass.services.call(
                        "input_number",
                        "set_value",
                        {
                            "entity_id": "input_number.pumpsteer_integral_gain",
                            "value": round(suggested_gain, 3),
                        },
                    )
                    msg = f"🤖 Auto-Tune: Adjusted integral_gain {current_gain} → {suggested_gain:.3f}. {reason}"
                    self.hass.services.call(
                        "persistent_notification",
                        "create",
                        {
                            "title": "PumpSteer ML Auto-Tune (Gain)",
                            "message": msg,
                            "notification_id": "pumpsteer_autotune_gain",
                        },
                    )
                    notifications.append(
                        f"✅ AUTO-ADJUSTED: integral_gain {current_gain} → {suggested_gain:.3f}"
                    )
                    _LOGGER.info(msg)
                    self.last_gain_adjustment = dt_util.now().isoformat()
                except Exception as e:
                    _LOGGER.error(f"Auto-tune (gain) failed: {e}")
                    notifications.append(f"❌ Gain auto-tune failed: {e}")
            else:
                tip_msg = f"💡 TIP: Consider changing integral_gain {current_gain} → {suggested_gain:.3f}. {reason}"
                self.hass.services.call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "PumpSteer ML Recommendation (Gain)",
                        "message": tip_msg,
                        "notification_id": "pumpsteer_recommendation_gain",
                    },
                )
                notifications.append(
                    f"💡 RECOMMENDATION: integral_gain {current_gain} → {suggested_gain:.3f} ({reason})"
                )

            return {
                "action": "auto_tune" if auto_tune_enabled else "recommendation",
                "old_value": current_gain,
                "new_value": suggested_gain,
                "reason": reason,
                "notifications": notifications,
            }

        except Exception as e:
            _LOGGER.error(f"Error in gain auto-tune check: {e}")
            return None
