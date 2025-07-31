# ml_adaptive.py

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

# Importera HomeAssistant och dt_util för asynkron körning och korrekt tidsstämpling
from homeassistant.core import HomeAssistant # Lade till detta
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

class PumpSteerMLCollector:
    """
    Samlar data för maskininlärning utan att påverka befintlig logik.
    Bara observerar och lär sig - gör inga förändringar än.
    """

    # ÄNDRAD: Nu tar konstruktorn emot 'hass'
    def __init__(self, hass: HomeAssistant, data_file_path: str = "/config/pumpsteer_ml_data.json"):
        """
        Initialiserar ML-datainsamlaren.

        Args:
            hass: HomeAssistant-instansen för asynkron operationer.
            data_file_path: Sökväg till JSON-filen för att spara/ladda data.
        """
        self.hass = hass # Spara hass-instansen för executor_job
        self.data_file = data_file_path
        self.learning_sessions = []
        self.current_session = None
        # self.load_data() # TA BORT DENNA RAD HÄR! LADDNING SKER ASYNKRONT!
        _LOGGER.info("PumpSteer ML Collector initialized (observation mode). Data will be loaded asynchronously.")

    # NY FUNKTION: Asynkron laddning av data
    async def async_load_data(self) -> None:
        """Ladda sparad data från fil asynkront."""
        try:
            # Använd hass.async_add_executor_job för blockerande fil-I/O
            await self.hass.async_add_executor_job(self._load_data_sync)
            _LOGGER.info(f"ML: Loaded {len(self.learning_sessions)} previous sessions from {self.data_file}")
        except Exception as e:
            _LOGGER.error(f"ML: Error loading data asynchronously: {e}")
            self.learning_sessions = [] # Se till att sessions-listan är tom vid fel

    # NY FUNKTION: Synkron version av laddning för executor
    def _load_data_sync(self) -> None:
        """Synkron logik för att ladda data, körs i executor."""
        if not Path(self.data_file).exists():
            _LOGGER.debug(f"ML: No existing data file found at {self.data_file}, starting fresh.")
            return

        with open(self.data_file, 'r') as f:
            data = json.load(f)

        self.learning_sessions = data.get("sessions", [])

    # NY FUNKTION: Asynkron sparande av data
    async def async_save_data(self) -> None:
        """Spara insamlad data till fil asynkront."""
        try:
            await self.hass.async_add_executor_job(self._save_data_sync)
            _LOGGER.debug(f"ML: Saved {len(self.learning_sessions)} sessions to {self.data_file}")
        except Exception as e:
            _LOGGER.error(f"ML: Error saving data asynchronously: {e}")

    # NY FUNKTION: Synkron version av sparande för executor
    def _save_data_sync(self) -> None:
        """Synkron logik för att spara data, körs i executor."""
        data = {
            "version": "1.0",
            "created": dt_util.now().isoformat(), # Använd dt_util.now()
            "sessions": self.learning_sessions[-100:],  # Spara bara senaste 100 sessionerna
            "session_count": len(self.learning_sessions)
        }
        Path(self.data_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)

    def start_session(self, initial_data: Dict[str, Any]) -> None:
        """
        Starta en ny lärande session.
        ...
        """
        if self.current_session is not None:
            self.end_session("interrupted")

        self.current_session = {
            "start_time": dt_util.now().isoformat(), # Använd dt_util.now()
            "initial": initial_data.copy(),
            "updates": [],
            "end_result": None
        }

        _LOGGER.debug(f"ML: Started learning session - Mode: {initial_data.get('mode', 'unknown')}")

    def update_session(self, update_data: Dict[str, Any]) -> None:
        """
        Uppdatera pågående session med ny data.
        ...
        """
        if self.current_session is None:
            return

        update_entry = {
            "timestamp": dt_util.now().isoformat(), # Använd dt_util.now()
            "data": update_data.copy()
        }

        self.current_session["updates"].append(update_entry)

        if len(self.current_session["updates"]) > 100:
            self.current_session["updates"] = self.current_session["updates"][-50:]

    def end_session(self, reason: str = "normal", final_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Avsluta pågående session och spara resultatet.
        ...
        """
        if self.current_session is None:
            return

        self.current_session["end_time"] = dt_util.now().isoformat() # Använd dt_util.now()
        self.current_session["end_reason"] = reason
        self.current_session["end_result"] = final_data

        session_summary = self._analyze_session(self.current_session)
        self.current_session["summary"] = session_summary

        self.learning_sessions.append(self.current_session)
        self.current_session = None

        # ÄNDRAD: Spara till fil asynkront
        self.hass.loop.create_task(self.async_save_data()) # Skapa en task för att spara asynkront

        _LOGGER.debug(f"ML: Session ended - Reason: {reason}, Duration: {session_summary.get('duration_minutes', 0):.1f}min")

    def _analyze_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Analysera en avslutad session och extrahera lärdomar."""
        # ... (ingen ändring här)
        pass

    def _calculate_stability(self, updates: List[Dict]) -> float:
        """Beräkna hur stabil temperaturen var under sessionen."""
        # ... (ingen ändring här)
        pass

    def get_learning_insights(self) -> Dict[str, Any]:
        """
        Hämta insikter från insamlad data utan att påverka systemet.
        ...
        """
        # ... (ingen ändring här)
        pass

    def _analyze_performance_by_setting(self, performance_dict: Dict) -> Dict:
        """Analysera prestanda för olika inställningar."""
        # ... (ingen ändring här)
        pass

    def _generate_simple_recommendations(self) -> List[str]:
        """Generera enkla rekommendationer baserat på data."""
        # ... (ingen ändring här)
        pass

    # load_data och save_data är nu de nya async/sync paren ovan.
    # Du kan ta bort de gamla synkrona metoderna om du hade dem.

    def get_status(self) -> Dict[str, Any]:
        """Hämta aktuell status för ML-systemet."""
        return {
            "collecting_data": True,
            "making_recommendations": len(self.learning_sessions) >= 5,
            "sessions_collected": len(self.learning_sessions),
            "current_session_active": self.current_session is not None,
            "data_file": self.data_file,
            "ready_for_insights": len(self.learning_sessions) >= 5
        }
