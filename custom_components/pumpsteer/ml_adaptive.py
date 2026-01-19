#   This version extends the original ML collector with richer data logging,
#   session summaries, and a simple self-learning regression model that
#   derives optimal inertia and aggressiveness based on comfort drift and
#   duration performance.


from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import json
import logging
import statistics
import numpy as np


from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .ml_settings import (
    ML_MODULE_VERSION,
    ML_STORAGE_KEY,
    ML_STORAGE_VERSION,
    ML_LEGACY_DATA_FILENAME,
    ML_MAX_SAVED_SESSIONS,
    ML_MAX_SESSION_UPDATES,
    ML_TRIMMED_UPDATES,
    ML_SUCCESS_TEMP_DIFF_THRESHOLD,
    ML_DATA_VERSION,
    ML_NOTIFICATION_PREFIX,
    ML_DEBUG_MODE,
)

_LOGGER = logging.getLogger(__name__)


class PumpSteerMLCollector:
    """Collects, analyzes, and learns from PumpSteer operation sessions"""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._store = Store(hass, ML_STORAGE_VERSION, ML_STORAGE_KEY)
        self._legacy_data_path = hass.config.path(ML_LEGACY_DATA_FILENAME)
        self.learning_sessions: List[Dict[str, Any]] = []
        self.current_session: Optional[Dict[str, Any]] = None
        self.learning_summary: Dict[str, Any] = {}
        self.model_coefficients: Optional[List[float]] = None

        if ML_DEBUG_MODE:
            _LOGGER.setLevel(logging.DEBUG)

        _LOGGER.info(
            "%s ML Collector initialized (v%s) - learning and adaptive mode enabled.",
            ML_NOTIFICATION_PREFIX,
            ML_MODULE_VERSION,
        )

    async def async_load_data(self) -> None:
        """Load previously saved learning data from disk"""
        data = await self._store.async_load()
        source = "storage"
        if data is None:
            data = await self._async_load_legacy_data()
            if data is not None:
                source = "legacy file"
            else:
                data = self._default_payload()
                source = "defaults"

        if not isinstance(data, dict):
            _LOGGER.warning("ML: Unexpected data format; resetting to defaults.")
            data = self._default_payload()

        if data.get("version", "unknown") != ML_DATA_VERSION:
            data = await self._async_handle_version_mismatch(data)
            source = f"{source} (migrated)"

        await self._store.async_save(data)
        self._apply_loaded_data(data)
        _LOGGER.info(
            "ML: Loaded %d sessions from %s", len(self.learning_sessions), source
        )

    async def _async_load_legacy_data(self) -> Optional[Dict[str, Any]]:
        return await self.hass.async_add_executor_job(self._load_legacy_data_sync)

    def _load_legacy_data_sync(self) -> Optional[Dict[str, Any]]:
        legacy_path = Path(self._legacy_data_path)
        if not legacy_path.exists():
            _LOGGER.debug("ML: No legacy data file found.")
            return None

        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            _LOGGER.warning(
                "ML: Failed to read legacy data file %s (%s). Using defaults.",
                legacy_path,
                exc,
            )
            return None

        _LOGGER.info("ML: Imported legacy data from %s", legacy_path)
        return data

    async def _async_handle_version_mismatch(
        self, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Try to migrate mismatched data; otherwise reset to defaults."""
        migrated = self._migrate_data(data)
        if migrated is None:
            _LOGGER.warning("ML: Unable to migrate data; resetting to defaults.")
            defaults = self._default_payload()
            await self._store.async_save(defaults)
            return defaults

        if migrated.get("version") != ML_DATA_VERSION:
            migrated["version"] = ML_DATA_VERSION
        migrated.setdefault("ml_module_version", ML_MODULE_VERSION)
        migrated.setdefault("created", dt_util.now().isoformat())
        migrated.setdefault("session_count", len(migrated.get("sessions", [])))
        await self._store.async_save(migrated)
        return migrated

    def _migrate_data(self, data: Any) -> Optional[Dict[str, Any]]:
        """Attempt a simple migration by adding missing fields with defaults."""
        if not isinstance(data, dict):
            return None

        migrated = dict(data)
        sessions = migrated.get("sessions")
        if sessions is None:
            migrated["sessions"] = []
        elif not isinstance(sessions, list):
            return None

        if "learning_summary" not in migrated or not isinstance(
            migrated.get("learning_summary"), dict
        ):
            migrated["learning_summary"] = {}

        if "model_coefficients" not in migrated:
            migrated["model_coefficients"] = None

        normalized_sessions: List[Dict[str, Any]] = []
        for session in migrated.get("sessions", []):
            if not isinstance(session, dict):
                continue
            normalized = dict(session)
            normalized.setdefault("updates", [])
            normalized.setdefault("initial", {})
            normalized.setdefault("summary", {})
            normalized_sessions.append(normalized)

        migrated["sessions"] = normalized_sessions
        return migrated

    def _default_payload(self) -> Dict[str, Any]:
        return {
            "version": ML_DATA_VERSION,
            "ml_module_version": ML_MODULE_VERSION,
            "created": dt_util.now().isoformat(),
            "sessions": [],
            "session_count": 0,
            "learning_summary": {},
            "model_coefficients": None,
        }

    def _apply_loaded_data(self, data: Dict[str, Any]) -> None:
        self.learning_sessions = data.get("sessions", [])
        self.learning_summary = data.get("learning_summary", {})
        self.model_coefficients = data.get("model_coefficients", None)

    async def async_save_data(self) -> None:
        data = {
            "version": ML_DATA_VERSION,
            "ml_module_version": ML_MODULE_VERSION,
            "created": dt_util.now().isoformat(),
            "sessions": self.learning_sessions[-ML_MAX_SAVED_SESSIONS:],
            "session_count": len(self.learning_sessions),
            "learning_summary": self.learning_summary,
            "model_coefficients": self.model_coefficients,
        }

        await self._store.async_save(data)

    def start_session(self, initial_data: Dict[str, Any]) -> None:
        """Start a new learning session"""
        if self.current_session is not None:
            self.end_session("interrupted")

        self.current_session = {
            "start_time": dt_util.now().isoformat(),
            "initial": initial_data.copy(),
            "updates": [],
        }

        _LOGGER.debug(
            "ML: New session started (mode=%s)", initial_data.get("mode", "unknown")
        )

    def update_session(self, update_data: Dict[str, Any]) -> None:
        """Add detailed data points to the ongoing session"""
        if self.current_session is None:
            return

        extended_data = {
            "timestamp": dt_util.now().isoformat(),
            "data": {
                "indoor_temp": update_data.get("indoor_temp"),
                "target_temp": update_data.get("target_temp"),
                "outdoor_temp": update_data.get("outdoor_temp"),
                "price_now": update_data.get("price_now"),
                "mode": update_data.get("mode", "unknown"),
                "heating_active": update_data.get("heating_active", False),
                "aggressiveness": update_data.get("aggressiveness", 0),
                "inertia": update_data.get("inertia", 1.0),
                "fake_outdoor_temp": update_data.get("fake_outdoor_temp"),
                "heat_demand": update_data.get("heat_demand"),
                "house_inertia": update_data.get("house_inertia"),
            },
        }

        self.current_session["updates"].append(extended_data)

        if len(self.current_session["updates"]) > ML_MAX_SESSION_UPDATES:
            self.current_session["updates"] = self.current_session["updates"][
                -ML_TRIMMED_UPDATES:
            ]

    def end_session(
        self, reason: str = "normal", final_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Close the session, summarize it, and learn from results"""
        if self.current_session is None:
            return

        self.current_session["end_time"] = dt_util.now().isoformat()
        self.current_session["end_reason"] = reason
        self.current_session["end_result"] = final_data

        updates = self.current_session.get("updates", [])
        if not updates:
            _LOGGER.warning("ML: Session ended without updates.")
            return

        indoor_temps = [
            u["data"].get("indoor_temp")
            for u in updates
            if u["data"].get("indoor_temp") is not None
        ]
        outdoor_temps = [
            u["data"].get("outdoor_temp")
            for u in updates
            if u["data"].get("outdoor_temp") is not None
        ]
        prices = [
            u["data"].get("price_now")
            for u in updates
            if u["data"].get("price_now") is not None
        ]
        targets = [
            u["data"].get("target_temp")
            for u in updates
            if u["data"].get("target_temp") is not None
        ]

        first_temp = indoor_temps[0] if indoor_temps else 0
        last_temp = indoor_temps[-1] if indoor_temps else 0
        temp_rise = last_temp - first_temp
        avg_price = statistics.mean(prices) if prices else 0
        avg_outdoor = statistics.mean(outdoor_temps) if outdoor_temps else None
        comfort_drift = abs(targets[-1] - last_temp) if targets else 0

        start_time = datetime.fromisoformat(self.current_session["start_time"])
        end_time = datetime.fromisoformat(self.current_session["end_time"])
        duration_minutes = (end_time - start_time).total_seconds() / 60

        initial = self.current_session.get("initial", {})
        mode = initial.get("mode", "unknown")
        aggressiveness = initial.get("aggressiveness", 0)
        inertia = initial.get("inertia", 1.0)

        summary = {
            "duration_minutes": round(duration_minutes, 1),
            "temp_rise": round(temp_rise, 2),
            "avg_price": round(avg_price, 3),
            "avg_outdoor_temp": round(avg_outdoor, 1)
            if avg_outdoor is not None
            else None,
            "comfort_drift": round(comfort_drift, 2),
            "aggressiveness": aggressiveness,
            "inertia": inertia,
            "mode": mode,
            "update_count": len(updates),
            "success": comfort_drift < ML_SUCCESS_TEMP_DIFF_THRESHOLD,
        }

        self.current_session["summary"] = summary
        self.learning_sessions.append(self.current_session)
        self.current_session = None

        _LOGGER.info(
            "ML: Session summary: ΔT=%.2f°C, drift=%.2f°C, dur=%.1fmin, aggr=%s, inertia=%s",
            temp_rise,
            comfort_drift,
            duration_minutes,
            aggressiveness,
            inertia,
        )

        # Trigger learning update
        self.hass.async_create_task(self._async_update_learning_model())
        self.hass.async_create_task(self.async_save_data())

    async def _async_update_learning_model(self) -> None:
        """Run the regression update in the executor to avoid blocking."""
        await self.hass.async_add_executor_job(self._update_learning_model)

    def _update_learning_model(self) -> None:
        """Perform a simple regression analysis on collected sessions"""
        heating_sessions = [
            s
            for s in self.learning_sessions
            if s.get("summary", {}).get("mode") == "heating"
        ]

        valid_summaries: List[Dict[str, Any]] = []
        skipped_sessions = 0

        for session in heating_sessions:
            summary = session.get("summary", {})

            comfort_drift = summary.get("comfort_drift")
            duration = summary.get("duration_minutes")
            aggressiveness = summary.get("aggressiveness")
            inertia = summary.get("inertia")

            if comfort_drift is None or duration is None:
                skipped_sessions += 1
                continue

            valid_summaries.append(
                {
                    "comfort_drift": comfort_drift,
                    "duration_minutes": duration,
                    "aggressiveness": aggressiveness
                    if aggressiveness is not None
                    else 0,
                    "inertia": inertia if inertia is not None else 1.0,
                }
            )

        if skipped_sessions:
            _LOGGER.warning(
                "ML: Skipped %s heating sessions missing comfort drift or duration data",
                skipped_sessions,
            )

        if len(valid_summaries) < 5:
            _LOGGER.debug("ML: Not enough sessions for regression learning.")
            return

        x = []
        y = []
        for summary in valid_summaries[-50:]:
            aggr = summary.get("aggressiveness", 0)
            inertia = summary.get("inertia", 1.0)
            dur = summary.get("duration_minutes", 0)
            drift = summary.get("comfort_drift", 0)
            x.append([aggr, inertia, dur])
            y.append(drift)

        a = np.column_stack((np.array(x), np.ones(len(x))))
        coeff, *_ = np.linalg.lstsq(a, np.array(y), rcond=None)
        self.model_coefficients = coeff.tolist()

        self.learning_summary = {
            "total_sessions": len(valid_summaries),
            "avg_duration": round(
                statistics.mean([s["duration_minutes"] for s in valid_summaries]),
                1,
            ),
            "avg_drift": round(
                statistics.mean([s["comfort_drift"] for s in valid_summaries]), 2
            ),
            "avg_inertia": round(
                statistics.mean([s["inertia"] for s in valid_summaries]), 2
            ),
            "avg_aggressiveness": round(
                statistics.mean([s["aggressiveness"] for s in valid_summaries]), 2
            ),
            "coefficients": [round(c, 4) for c in coeff],
            "updated": dt_util.now().isoformat(),
        }

        _LOGGER.info(
            "ML: Learning update complete — model coeff: %s",
            self.learning_summary["coefficients"],
        )

    def get_recommendations(self) -> List[str]:
        """Generate adaptive recommendations based on learned model"""
        if not self.model_coefficients:
            return ["System is still learning — need more sessions."]

        coeff = self.model_coefficients
        a, b, c, d = coeff

        msg = []
        msg.append(
            f"Learned model: drift ≈ {a:+.3f}·aggr + {b:+.3f}·inertia + {c:+.3f}·duration + {d:+.3f}"
        )

        if abs(a) > abs(b):
            msg.append("→ Aggressiveness affects comfort more than inertia.")
        else:
            msg.append("→ Inertia has stronger influence on comfort drift.")

        if a > 0:
            msg.append("Higher aggressiveness increases comfort drift (less stable).")
        else:
            msg.append("Higher aggressiveness reduces comfort drift (more stable).")

        if b > 0:
            msg.append("Higher inertia may worsen drift slightly (too sluggish).")
        else:
            msg.append("Higher inertia improves stability (responds faster).")

        msg.append("System continues to refine model with every new heating session.")
        return msg

    def get_learning_summary(self) -> Dict[str, Any]:
        """Return current learning summary and model state"""
        return {
            "summary": self.learning_summary,
            "coefficients": self.model_coefficients,
            "total_sessions": len(self.learning_sessions),
            "last_updated": dt_util.now().isoformat(),
        }

    async def async_shutdown(self) -> None:
        """Graceful shutdown and data save"""
        if self.current_session is not None:
            self.end_session("shutdown")
        await self.async_save_data()
        _LOGGER.info("ML: Collector shutdown complete.")
