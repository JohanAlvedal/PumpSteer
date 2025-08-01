# ml_adaptive.py - Förbättrad men enkel version

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
import statistics

# Importera HomeAssistant och dt_util för asynkron körning och korrekt tidsstämpling
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

class PumpSteerMLCollector:
    """
    Samlar data för maskininlärning och ger grundläggande analys.
    Förbättrad version med enkla rekommendationer och trender.
    """

    def __init__(self, hass: HomeAssistant, data_file_path: str = "/config/pumpsteer_ml_data.json"):
        """
        Initialiserar ML-datainsamlaren.

        Args:
            hass: HomeAssistant-instansen för asynkron operationer.
            data_file_path: Sökväg till JSON-filen för att spara/ladda data.
        """
        self.hass = hass
        self.data_file = data_file_path
        self.learning_sessions = []
        self.current_session = None
        self.last_inertia_adjustment = None  # Spåra senaste justering
        _LOGGER.info("PumpSteer Enhanced ML Collector initialized (observation + analysis + auto-tune mode)")

    async def async_load_data(self) -> None:
        """Ladda sparad data från fil asynkront."""
        try:
            await self.hass.async_add_executor_job(self._load_data_sync)
            _LOGGER.info(f"ML: Loaded {len(self.learning_sessions)} previous sessions from {self.data_file}")
        except Exception as e:
            _LOGGER.error(f"ML: Error loading data asynchronously: {e}")
            self.learning_sessions = []

    def _load_data_sync(self) -> None:
        """Synkron logik för att ladda data, körs i executor."""
        if not Path(self.data_file).exists():
            _LOGGER.debug(f"ML: No existing data file found at {self.data_file}, starting fresh.")
            return

        with open(self.data_file, 'r') as f:
            data = json.load(f)

        self.learning_sessions = data.get("sessions", [])

    async def async_save_data(self) -> None:
        """Spara insamlad data till fil asynkront."""
        try:
            await self.hass.async_add_executor_job(self._save_data_sync)
            _LOGGER.debug(f"ML: Saved {len(self.learning_sessions)} sessions to {self.data_file}")
        except Exception as e:
            _LOGGER.error(f"ML: Error saving data asynchronously: {e}")

    def _save_data_sync(self) -> None:
        """Synkron logik för att spara data, körs i executor."""
        data = {
            "version": "1.0",
            "created": dt_util.now().isoformat(),
            "sessions": self.learning_sessions[-100:],  # Spara bara senaste 100 sessionerna
            "session_count": len(self.learning_sessions)
        }
        Path(self.data_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)

    def start_session(self, initial_data: Dict[str, Any]) -> None:
        """Starta en ny lärande session."""
        if self.current_session is not None:
            self.end_session("interrupted")

        self.current_session = {
            "start_time": dt_util.now().isoformat(),
            "initial": initial_data.copy(),
            "updates": [],
            "end_result": None
        }

        _LOGGER.debug(f"ML: Started learning session - Mode: {initial_data.get('mode', 'unknown')}")

    def update_session(self, update_data: Dict[str, Any]) -> None:
        """Uppdatera pågående session med ny data."""
        if self.current_session is None:
            return

        update_entry = {
            "timestamp": dt_util.now().isoformat(),
            "data": update_data.copy()
        }

        self.current_session["updates"].append(update_entry)

        if len(self.current_session["updates"]) > 100:
            self.current_session["updates"] = self.current_session["updates"][-50:]

    def end_session(self, reason: str = "normal", final_data: Optional[Dict[str, Any]] = None) -> None:
        """Avsluta pågående session och spara resultatet."""
        if self.current_session is None:
            return

        self.current_session["end_time"] = dt_util.now().isoformat()
        self.current_session["end_reason"] = reason
        self.current_session["end_result"] = final_data

        # Analysera sessionen
        session_summary = self._analyze_session(self.current_session)
        self.current_session["summary"] = session_summary

        self.learning_sessions.append(self.current_session)
        self.current_session = None

        # Spara till fil asynkront
        self.hass.loop.create_task(self.async_save_data())

        _LOGGER.debug(f"ML: Session ended - Reason: {reason}, Duration: {session_summary.get('duration_minutes', 0):.1f}min")

    def _analyze_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Analysera en avslutad session och extrahera lärdomar."""
        try:
            start_time = datetime.fromisoformat(session["start_time"])
            end_time = datetime.fromisoformat(session["end_time"])
            duration_minutes = (end_time - start_time).total_seconds() / 60

            initial = session.get("initial", {})
            updates = session.get("updates", [])
            
            # Grundläggande analys
            summary = {
                "duration_minutes": round(duration_minutes, 1),
                "mode": initial.get("mode", "unknown"),
                "aggressiveness": initial.get("aggressiveness", 0),
                "inertia": initial.get("inertia", 1.0),
                "update_count": len(updates),
                "start_temp_diff": initial.get("indoor_temp", 0) - initial.get("target_temp", 0),
            }

            # Klassificera session som framgångsrik eller inte
            if duration_minutes < 120 and abs(summary["start_temp_diff"]) > 0.3:  # Under 2h för betydande temperaturskillnad
                summary["success"] = True
            elif duration_minutes > 180:  # Över 3h indikerar problem
                summary["success"] = False
            else:
                summary["success"] = None  # Neutral/oklart

            return summary

        except Exception as e:
            _LOGGER.error(f"ML: Error analyzing session: {e}")
            return {"duration_minutes": 0, "success": None, "mode": "error"}

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

    # === NYA FÖRBÄTTRADE FUNKTIONER ===

    def get_performance_summary(self) -> Dict[str, Any]:
        """Hämta prestanda-sammanfattning baserat på insamlade sessions."""
        if len(self.learning_sessions) < 3:
            return {
                "status": "insufficient_data",
                "message": f"Behöver minst 3 sessions för analys. Har {len(self.learning_sessions)}."
            }

        try:
            # Analysera alla sessions
            heating_sessions = [s for s in self.learning_sessions 
                             if s.get("summary", {}).get("mode") == "heating"]
            
            if not heating_sessions:
                return {
                    "status": "no_heating_data",
                    "message": "Inga heating-sessions att analysera än."
                }

            # Beräkna statistik
            durations = [s["summary"]["duration_minutes"] for s in heating_sessions 
                        if s.get("summary", {}).get("duration_minutes", 0) > 0]
            
            aggressiveness_values = [s["summary"]["aggressiveness"] for s in heating_sessions
                                   if s.get("summary", {}).get("aggressiveness") is not None]

            successful_sessions = [s for s in heating_sessions 
                                 if s.get("summary", {}).get("success") is True]

            # Sammanställ resultat
            summary = {
                "status": "analyzing",
                "total_heating_sessions": len(heating_sessions),
                "avg_heating_duration": round(statistics.mean(durations), 1) if durations else 0,
                "success_rate": round(len(successful_sessions) / len(heating_sessions) * 100, 1),
                "most_used_aggressiveness": round(statistics.mode(aggressiveness_values), 1) if aggressiveness_values else 0,
                "sessions_analyzed": len(self.learning_sessions)
            }

            return summary

        except Exception as e:
            _LOGGER.error(f"ML: Error in performance summary: {e}")
            return {"status": "error", "message": str(e)}

    def get_recommendations(self) -> List[str]:
        """Generera enkla rekommendationer baserat på insamlad data enligt korrekt design-filosofi."""
        performance = self.get_performance_summary()
        
        if performance.get("status") != "analyzing":
            return ["Samlar fortfarande data för att ge rekommendationer..."]

        recommendations = []

        try:
            # Analysera sessions för att hitta mönster
            heating_sessions = [s for s in self.learning_sessions 
                             if s.get("summary", {}).get("mode") == "heating"]
            
            if not heating_sessions:
                return ["Inga heating-sessions att analysera än."]

            # Samla data för analys
            avg_duration = performance.get("avg_heating_duration", 0)
            success_rate = performance.get("success_rate", 0)
            most_used_agg = performance.get("most_used_aggressiveness", 3)

            # Analysera inertia vs duration patterns
            inertia_values = [s["summary"].get("inertia", 1.0) for s in heating_sessions[-10:]]
            avg_inertia = statistics.mean(inertia_values) if inertia_values else 1.0

            # AGGRESSIVENESS-rekommendationer (pengarbesparings-verktyg 0-5)
            if most_used_agg == 0:
                recommendations.append("Aggressivitet 0: Ingen pengarbesparings-logik aktiv. Systemet fungerar som vanlig termostat.")
            elif most_used_agg >= 4 and success_rate < 70:
                recommendations.append(f"Aggressivitet {most_used_agg} ger hög besparing men låg komfort ({success_rate:.1f}% framgång). Överväg att minska till {most_used_agg-1} för bättre balans.")
            elif most_used_agg <= 2 and avg_duration < 45:
                recommendations.append(f"Aggressivitet {most_used_agg} prioriterar komfort. Du kan öka till {most_used_agg+1} för mer pengarbesparingar om komforten är acceptabel.")

            # HOUSE_INERTIA-rekommendationer (husets tröghet 0-5)
            if avg_duration > 120 and avg_inertia < 2.0:
                recommendations.append(f"Heating tar lång tid ({avg_duration:.1f}min) med house_inertia {avg_inertia:.1f}. Ditt hus kanske är tröghare - testa att öka house_inertia till {avg_inertia + 0.5:.1f}.")
            elif avg_duration < 20 and avg_inertia > 2.0:
                recommendations.append(f"Väldigt korta heating-sessions ({avg_duration:.1f}min) med house_inertia {avg_inertia:.1f}. Ditt hus reagerar snabbt - överväg att minska house_inertia till {avg_inertia - 0.5:.1f}.")

            # KOMBINATIONS-analys (aggressivitet + inertia)
            if most_used_agg >= 4 and avg_inertia <= 1.0:
                recommendations.append("Hög aggressivitet (4-5) + låg house_inertia (0-1): Risk för temperatursvängningar i snabbt hus med hög besparing.")
            elif most_used_agg <= 1 and avg_inertia >= 4.0:
                recommendations.append("Låg aggressivitet (0-1) + hög house_inertia (4-5): Stabilt men dyrare i trögt hus med komfortprioritet.")

            # SUCCESS RATE-analys
            if success_rate > 85:
                recommendations.append(f"Utmärkt balans mellan besparing och komfort ({success_rate:.1f}% framgång)! Nuvarande inställningar fungerar bra.")
            elif success_rate < 60:
                recommendations.append(f"Låg framgångsgrad ({success_rate:.1f}%). Justera antingen aggressivitet (besparing/komfort-balans) eller house_inertia (husets tröghet).")

            # Generell rådgivning
            if len(self.learning_sessions) < 10:
                recommendations.append("Systemet lär sig fortfarande. Vänta med större ändringar tills 10+ sessions samlats.")

            # DESIGN-FILOSOFI påminnelse
            if len(recommendations) == 0:
                recommendations.append("Påminnelse: Aggressivitet (0-5) = pengarbesparingar vs komfort. House_inertia (0-5) = husets temperaturtröghet.")

            return recommendations

        except Exception as e:
            _LOGGER.error(f"ML: Error generating recommendations: {e}")
            return ["Fel vid generering av rekommendationer."]

    def get_learning_insights(self) -> Dict[str, Any]:
        """Kombinera all information + kontrollera auto-tune möjligheter."""
        try:
            status = self.get_status()
            performance = self.get_performance_summary()
            recommendations = self.get_recommendations()
            
            # Kontrollera om auto-tune ska köras
            if len(self.learning_sessions) >= 5:  # Minst 5 sessions för auto-tune
                auto_tune_result = self._check_auto_tune_inertia()
                if auto_tune_result:
                    recommendations.extend(auto_tune_result.get("notifications", []))

            return {
                "ml_status": status,
                "performance": performance,
                "recommendations": recommendations,
                "last_updated": dt_util.now().isoformat()
            }

        except Exception as e:
            _LOGGER.error(f"ML: Error getting learning insights: {e}")
            return {
                "error": str(e),
                "ml_status": self.get_status()
            }

    def _check_auto_tune_inertia(self) -> Optional[Dict[str, Any]]:
        """Kontrollera om house_inertia behöver justeras och utför vid behov."""
        try:
            # Hämta auto-tune setting
            auto_tune_state = self.hass.states.get("input_boolean.autotune_inertia")
            auto_tune_enabled = auto_tune_state and auto_tune_state.state == "on"
            
            # Hämta nuvarande inertia
            current_inertia_state = self.hass.states.get("input_number.house_inertia")
            if not current_inertia_state:
                return None
            
            current_inertia = float(current_inertia_state.state)
            
            # Analysera senaste 10 heating sessions
            recent_heating = [s for s in self.learning_sessions[-10:] 
                            if s.get("summary", {}).get("mode") == "heating"]
            
            if len(recent_heating) < 3:
                return None
                
            # Analysera prestanda-mönster
            avg_duration = statistics.mean([s["summary"]["duration_minutes"] 
                                          for s in recent_heating 
                                          if s.get("summary", {}).get("duration_minutes", 0) > 0])
            
            # Bestäm om justering behövs
            suggested_inertia = current_inertia
            reason = ""
            action_needed = False
            
            if avg_duration > 90 and current_inertia < 3.0:  # Långa sessions
                suggested_inertia = min(current_inertia + 0.3, 5.0)
                reason = f"Heating tar i snitt {avg_duration:.1f}min - ditt hus verkar tröghare än inställt"
                action_needed = True
                
            elif avg_duration < 25 and current_inertia > 0.5:  # Mycket korta sessions
                # Kontrollera om det är överskjutning (skulle kräva mer analys)
                suggested_inertia = max(current_inertia - 0.2, 0.1)
                reason = f"Mycket korta heating-sessions ({avg_duration:.1f}min) - huset reagerar snabbare än förväntat"
                action_needed = True
            
            if not action_needed:
                return None
                
            # Undvik för frekventa justeringar
            if (self.last_inertia_adjustment and 
                (dt_util.now() - datetime.fromisoformat(self.last_inertia_adjustment)).days < 2):
                return None
            
            notifications = []
            
            if auto_tune_enabled:
                # AUTOMATISK JUSTERING
                try:
                    self.hass.services.call(
                        "input_number", "set_value",
                        {
                            "entity_id": "input_number.house_inertia", 
                            "value": round(suggested_inertia, 1)
                        }
                    )
                    
                    # Skicka notification
                    notification_msg = (f"🤖 Auto-Tune: Justerade house_inertia "
                                      f"{current_inertia} → {suggested_inertia:.1f}. "
                                      f"Orsak: {reason}. Övervakar prestanda...")
                    
                    self.hass.services.call(
                        "persistent_notification", "create",
                        {
                            "title": "PumpSteer ML Auto-Tune",
                            "message": notification_msg,
                            "notification_id": "pumpsteer_autotune"
                        }
                    )
                    
                    notifications.append(f"✅ AUTO-JUSTERAT: house_inertia {current_inertia} → {suggested_inertia:.1f}")
                    self.last_inertia_adjustment = dt_util.now().isoformat()
                    
                    _LOGGER.info(f"PumpSteer Auto-Tune: Adjusted house_inertia {current_inertia} → {suggested_inertia:.1f}")
                    
                except Exception as e:
                    _LOGGER.error(f"Auto-tune failed: {e}")
                    notifications.append(f"❌ Auto-tune misslyckades: {e}")
            else:
                # BARA TIPS/REKOMMENDATION
                tip_msg = (f"💡 TIP: Överväg att ändra house_inertia "
                          f"{current_inertia} → {suggested_inertia:.1f}. "
                          f"Orsak: {reason}")
                
                notifications.append(f"💡 REKOMMENDATION: house_inertia {current_inertia} → {suggested_inertia:.1f} ({reason})")
                
                # Även skicka som persistent notification för synlighet
                self.hass.services.call(
                    "persistent_notification", "create",
                    {
                        "title": "PumpSteer ML Rekommendation", 
                        "message": tip_msg,
                        "notification_id": "pumpsteer_recommendation"
                    }
                )
            
            return {
                "action": "auto_tune" if auto_tune_enabled else "recommendation",
                "old_value": current_inertia,
                "new_value": suggested_inertia,
                "reason": reason,
                "notifications": notifications
            }
            
        except Exception as e:
            _LOGGER.error(f"Error in auto-tune check: {e}")
            return None
