# enhanced_ml_adaptive.py
# Förbättrad ML-modul för PumpSteer med prediktiva modeller och adaptiva funktioner

import json
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from collections import defaultdict, deque
import statistics

# Importera HomeAssistant och dt_util för asynkron körning och korrekt tidsstämpling
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

class EnhancedPumpSteerMLCollector:
    """
    Avancerad ML-sammare för PumpSteer med prediktiva modeller och adaptiva funktioner.
    
    Nya funktioner:
    - Förutsäger optimala temperaturer baserat på historik
    - Lär sig från framgångar och misslyckanden
    - Adaptiv aggressivitet baserat på prestanda
    - Energioptimering genom inlärning
    - Rekommendationsmotor för förbättringar
    """

    def __init__(self, hass: HomeAssistant, data_file_path: str = "/config/pumpsteer_enhanced_ml_data.json"):
        """
        Initialiserar den förbättrade ML-datainsamlaren.

        Args:
            hass: HomeAssistant-instansen för asynkron operationer.
            data_file_path: Sökväg till JSON-filen för att spara/ladda data.
        """
        self.hass = hass
        self.data_file = data_file_path
        self.learning_sessions = []
        self.current_session = None
        
        # Nya ML-strukturer
        self.performance_history = deque(maxlen=1000)  # Senaste 1000 prestationsmätningar
        self.temperature_predictions = {}  # Cache för temperaturförutsägelser
        self.energy_efficiency_scores = defaultdict(list)  # Energieffektivitet per strategi
        self.adaptive_settings = {
            'optimal_aggressiveness': 3.0,
            'learning_rate': 0.1,
            'confidence_threshold': 0.7,
            'min_samples_for_prediction': 10
        }
        
        # Inlärningsmodeller (enkla statistiska modeller för start)
        self.temperature_model = SimpleTemperaturePredictor()
        self.efficiency_analyzer = EnergyEfficiencyAnalyzer()
        self.recommendation_engine = RecommendationEngine()
        
        _LOGGER.info("Enhanced PumpSteer ML Collector initialized with predictive capabilities.")

    # === ASYNKRON DATAHANTERING ===
    
    async def async_load_data(self) -> None:
        """Ladda sparad data från fil asynkront."""
        try:
            await self.hass.async_add_executor_job(self._load_data_sync)
            
            # Bygg modeller från laddad data
            await self._rebuild_models_from_history()
            
            _LOGGER.info(f"Enhanced ML: Loaded {len(self.learning_sessions)} sessions and rebuilt models")
        except Exception as e:
            _LOGGER.error(f"Enhanced ML: Error loading data: {e}")
            self.learning_sessions = []

    def _load_data_sync(self) -> None:
        """Synkron logik för att ladda data."""
        if not Path(self.data_file).exists():
            _LOGGER.debug(f"Enhanced ML: No existing data file, starting fresh.")
            return

        with open(self.data_file, 'r') as f:
            data = json.load(f)

        self.learning_sessions = data.get("sessions", [])
        self.performance_history = deque(data.get("performance_history", []), maxlen=1000)
        self.adaptive_settings.update(data.get("adaptive_settings", {}))
        
        # Ladda prediktionsdata om den finns
        predictions = data.get("temperature_predictions", {})
        self.temperature_predictions = {k: v for k, v in predictions.items()}

    async def async_save_data(self) -> None:
        """Spara insamlad data till fil asynkront."""
        try:
            await self.hass.async_add_executor_job(self._save_data_sync)
            _LOGGER.debug(f"Enhanced ML: Saved data with {len(self.learning_sessions)} sessions")
        except Exception as e:
            _LOGGER.error(f"Enhanced ML: Error saving data: {e}")

    def _save_data_sync(self) -> None:
        """Synkron logik för att spara data."""
        data = {
            "version": "2.0",  # Uppdaterad version för enhanced ML
            "created": dt_util.now().isoformat(),
            "sessions": self.learning_sessions[-200:],  # Spara fler sessioner för ML
            "performance_history": list(self.performance_history),
            "adaptive_settings": self.adaptive_settings,
            "temperature_predictions": dict(self.temperature_predictions),
            "session_count": len(self.learning_sessions),
            "model_statistics": self._get_model_statistics()
        }
        
        Path(self.data_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)

    # === FÖRBÄTTRAD SESSIONHANTERING ===

    def start_session(self, initial_data: Dict[str, Any]) -> None:
        """Starta en ny förbättrad lärande session."""
        if self.current_session is not None:
            self.end_session("interrupted")

        # Förutsäg optimal temperatur för denna situation
        predicted_temp = self.predict_optimal_temperature(initial_data)
        
        self.current_session = {
            "start_time": dt_util.now().isoformat(),
            "initial": initial_data.copy(),
            "predicted_optimal_temp": predicted_temp,
            "updates": [],
            "end_result": None,
            "performance_metrics": {
                "temperature_stability": [],
                "energy_efficiency_score": None,
                "target_achievement": None
            }
        }

        _LOGGER.debug(f"Enhanced ML: Started session - Mode: {initial_data.get('mode', 'unknown')}, "
                     f"Predicted optimal: {predicted_temp}°C")

    def update_session(self, update_data: Dict[str, Any]) -> None:
        """Uppdatera session med förbättrad analys."""
        if self.current_session is None:
            return

        update_entry = {
            "timestamp": dt_util.now().isoformat(),
            "data": update_data.copy()
        }

        # Beräkna prestationsmätningar
        if len(self.current_session["updates"]) > 0:
            performance = self._calculate_performance_metrics(update_data)
            update_entry["performance"] = performance
            self.current_session["performance_metrics"]["temperature_stability"].append(
                performance.get("stability_score", 0)
            )

        self.current_session["updates"].append(update_entry)

        # Begränsa uppdateringar för att spara minne
        if len(self.current_session["updates"]) > 100:
            self.current_session["updates"] = self.current_session["updates"][-50:]

    def end_session(self, reason: str = "normal", final_data: Optional[Dict[str, Any]] = None) -> None:
        """Avsluta session med förbättrad analys och inlärning."""
        if self.current_session is None:
            return

        self.current_session["end_time"] = dt_util.now().isoformat()
        self.current_session["end_reason"] = reason
        self.current_session["end_result"] = final_data

        # Beräkna slutgiltiga prestationsmätningar
        session_analysis = self._analyze_enhanced_session(self.current_session)
        self.current_session["analysis"] = session_analysis

        # Lägg till i prestandahistorik
        performance_record = {
            "timestamp": self.current_session["end_time"],
            "mode": self.current_session["initial"].get("mode", "unknown"),
            "aggressiveness": self.current_session["initial"].get("aggressiveness", 0),
            "success_score": session_analysis.get("success_score", 0),
            "energy_efficiency": session_analysis.get("energy_efficiency", 0),
            "temperature_accuracy": session_analysis.get("temperature_accuracy", 0)
        }
        self.performance_history.append(performance_record)

        # Uppdatera modeller med ny data
        self._update_models_with_session(self.current_session)

        # Uppdatera adaptiva inställningar
        self._update_adaptive_settings(session_analysis)

        self.learning_sessions.append(self.current_session)
        self.current_session = None

        # Spara asynkront
        self.hass.loop.create_task(self.async_save_data())

        _LOGGER.debug(f"Enhanced ML: Session ended - Success score: {session_analysis.get('success_score', 0):.2f}")

    # === PREDIKTIVA MODELLER ===

    def predict_optimal_temperature(self, conditions: Dict[str, Any]) -> float:
        """Förutsäg optimal temperatur baserat på aktuella förhållanden."""
        return self.temperature_model.predict(conditions)

    def predict_energy_consumption(self, mode: str, aggressiveness: float, duration_hours: float) -> float:
        """Förutsäg energiförbrukning för given strategi."""
        return self.efficiency_analyzer.predict_consumption(mode, aggressiveness, duration_hours)

    def get_adaptive_aggressiveness(self, conditions: Dict[str, Any]) -> float:
        """Få adaptiv aggressivitetsnivå baserat på inlärning."""
        base_aggressiveness = self.adaptive_settings['optimal_aggressiveness']
        
        # Justera baserat på aktuella förhållanden och historisk prestanda
        if len(self.performance_history) < 10:
            return base_aggressiveness
        
        # Hitta liknande förhållanden i historik
        similar_situations = self._find_similar_situations(conditions)
        if not similar_situations:
            return base_aggressiveness
        
        # Beräkna optimal aggressivitet från liknande situationer
        success_scores = [s['success_score'] for s in similar_situations]
        aggressiveness_values = [s['aggressiveness'] for s in similar_situations]
        
        if len(success_scores) >= 3:
            # Vikta aggressivitet med framgång
            weighted_agg = sum(a * s for a, s in zip(aggressiveness_values, success_scores))
            total_weight = sum(success_scores)
            if total_weight > 0:
                optimal_agg = weighted_agg / total_weight
                return max(0.0, min(5.0, optimal_agg))
        
        return base_aggressiveness

    # === ANALYS OCH REKOMMENDATIONER ===

    def get_enhanced_insights(self) -> Dict[str, Any]:
        """Hämta förbättrade insikter med prediktioner och rekommendationer."""
        if len(self.learning_sessions) < 5:
            return {
                "status": "learning",
                "message": "Samlar data för analys. Behöver minst 5 sessioner för insikter.",
                "sessions_collected": len(self.learning_sessions)
            }

        # Grundläggande statistik
        recent_sessions = self.learning_sessions[-50:]  # Senaste 50 sessionerna
        success_scores = [s.get('analysis', {}).get('success_score', 0) for s in recent_sessions]
        avg_success = statistics.mean(success_scores) if success_scores else 0

        # Energieffektivitetsanalys
        efficiency_analysis = self.efficiency_analyzer.analyze_efficiency_trends(recent_sessions)
        
        # Temperaturprediktioner
        prediction_accuracy = self._calculate_prediction_accuracy()
        
        # Rekommendationer
        recommendations = self.recommendation_engine.generate_recommendations(
            self.performance_history, self.adaptive_settings
        )

        return {
            "status": "analyzing",
            "overall_performance": {
                "success_rate": avg_success * 100,
                "total_sessions": len(self.learning_sessions),
                "recent_sessions": len(recent_sessions),
                "prediction_accuracy": prediction_accuracy * 100
            },
            "energy_efficiency": efficiency_analysis,
            "adaptive_settings": {
                "current_optimal_aggressiveness": self.adaptive_settings['optimal_aggressiveness'],
                "confidence_level": self.adaptive_settings['confidence_threshold'],
                "learning_progress": min(100, len(self.learning_sessions) / 50 * 100)
            },
            "predictions": {
                "temperature_model_accuracy": prediction_accuracy,
                "energy_model_status": "active" if len(self.performance_history) > 20 else "learning"
            },
            "recommendations": recommendations,
            "next_steps": self._generate_next_steps()
        }

    def get_situation_specific_advice(self, current_conditions: Dict[str, Any]) -> Dict[str, Any]:
        """Få situationsspecifika råd baserat på aktuella förhållanden."""
        predicted_temp = self.predict_optimal_temperature(current_conditions)
        adaptive_agg = self.get_adaptive_aggressiveness(current_conditions)
        energy_prediction = self.predict_energy_consumption(
            current_conditions.get('mode', 'normal'), 
            adaptive_agg, 
            1.0
        )
        
        return {
            "predicted_optimal_temperature": round(predicted_temp, 1),
            "recommended_aggressiveness": round(adaptive_agg, 1),
            "predicted_energy_consumption": round(energy_prediction, 2),
            "confidence": self._calculate_prediction_confidence(current_conditions),
            "similar_situations_found": len(self._find_similar_situations(current_conditions)),
            "advice": self._generate_situational_advice(current_conditions, predicted_temp, adaptive_agg)
        }

    # === HJÄLPMETODER ===

    async def _rebuild_models_from_history(self) -> None:
        """Bygg om modeller från historisk data."""
        if len(self.learning_sessions) < 5:
            return
        
        try:
            # Träna temperaturmodell
            training_data = []
            for session in self.learning_sessions[-100:]:  # Senaste 100 sessionerna
                if session.get('analysis') and session.get('initial'):
                    training_data.append({
                        'conditions': session['initial'],
                        'result': session['analysis']
                    })
            
            if training_data:
                await self.hass.async_add_executor_job(
                    self.temperature_model.train, training_data
                )
                
            _LOGGER.debug(f"Enhanced ML: Rebuilt models from {len(training_data)} training samples")
        except Exception as e:
            _LOGGER.error(f"Enhanced ML: Error rebuilding models: {e}")

    def _calculate_performance_metrics(self, update_data: Dict[str, Any]) -> Dict[str, float]:
        """Beräkna prestationsmätningar för en uppdatering."""
        metrics = {}
        
        # Temperaturstabilitet
        indoor_temp = update_data.get('indoor_temp')
        target_temp = update_data.get('target_temp')
        if indoor_temp is not None and target_temp is not None:
            temp_error = abs(indoor_temp - target_temp)
            metrics['temperature_error'] = temp_error
            metrics['stability_score'] = max(0, 1 - temp_error / 5.0)  # Normaliserad 0-1
        
        # Energieffektivitet (approximation baserad på mode och aggressivitet)
        mode = update_data.get('mode', 'normal')
        aggressiveness = update_data.get('aggressiveness', 0)
        fake_temp = update_data.get('fake_temp', 0)
        
        if mode in ['heating', 'cooling']:
            energy_usage = abs(fake_temp) * (1 + aggressiveness * 0.1)
            metrics['estimated_energy_usage'] = energy_usage
        
        return metrics

    def _analyze_enhanced_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Förbättrad sessionanalys med ML-fokus."""
        analysis = {}
        
        # Grundläggande sessioninfo
        start_time = datetime.fromisoformat(session['start_time'])
        end_time = datetime.fromisoformat(session['end_time'])
        duration = (end_time - start_time).total_seconds() / 60  # minuter
        
        analysis['duration_minutes'] = duration
        analysis['update_count'] = len(session.get('updates', []))
        
        # Temperaturprestanda
        temp_stability = session['performance_metrics'].get('temperature_stability', [])
        if temp_stability:
            analysis['avg_temperature_stability'] = statistics.mean(temp_stability)
            analysis['temperature_consistency'] = 1 - statistics.stdev(temp_stability) if len(temp_stability) > 1 else 1
        else:
            analysis['avg_temperature_stability'] = 0
            analysis['temperature_consistency'] = 0
        
        # Prediktionsnoggrannhet
        predicted_temp = session.get('predicted_optimal_temp')
        if predicted_temp and session.get('end_result'):
            actual_performance = analysis.get('avg_temperature_stability', 0)
            prediction_error = abs(predicted_temp - (session['initial'].get('target_temp', 20)))
            analysis['prediction_accuracy'] = max(0, 1 - prediction_error / 10.0)
        else:
            analysis['prediction_accuracy'] = 0.5  # Neutral om vi inte kan mäta
        
        # Övergripande framgångsmätning
        success_factors = [
            analysis.get('avg_temperature_stability', 0),
            analysis.get('temperature_consistency', 0), 
            analysis.get('prediction_accuracy', 0)
        ]
        analysis['success_score'] = statistics.mean(success_factors)
        
        # Energieffektivitet (förenklad)
        mode = session['initial'].get('mode', 'normal')
        aggressiveness = session['initial'].get('aggressiveness', 0)
        
        if mode in ['heating', 'cooling']:
            # Högre aggressivitet = mer energi, men kan vara motiverat
            efficiency_penalty = aggressiveness * 0.1
            stability_bonus = analysis.get('avg_temperature_stability', 0) * 0.5
            analysis['energy_efficiency'] = max(0, 1 - efficiency_penalty + stability_bonus)
        else:
            analysis['energy_efficiency'] = 0.8  # Neutral modes är ganska effektiva
        
        return analysis

    def _update_models_with_session(self, session: Dict[str, Any]) -> None:
        """Uppdatera modeller med data från avslutad session."""
        try:
            training_point = {
                'conditions': session['initial'],
                'result': session.get('analysis', {})
            }
            self.temperature_model.update(training_point)
            self.efficiency_analyzer.update(session)
        except Exception as e:
            _LOGGER.debug(f"Enhanced ML: Error updating models: {e}")

    def _update_adaptive_settings(self, session_analysis: Dict[str, Any]) -> None:
        """Uppdatera adaptiva inställningar baserat på sessionresultat."""
        success_score = session_analysis.get('success_score', 0)
        learning_rate = self.adaptive_settings['learning_rate']
        
        # Uppdatera optimal aggressivitet med exponentiell glidande medelvärde
        current_agg = self.adaptive_settings['optimal_aggressiveness']
        if self.current_session and 'initial' in self.current_session:
            session_agg = self.current_session['initial'].get('aggressiveness', current_agg)
            
            # Om sessionen var framgångsrik, flytta mot den aggressiviteten
            if success_score > 0.7:
                adjustment = (session_agg - current_agg) * learning_rate * success_score
                new_agg = current_agg + adjustment
                self.adaptive_settings['optimal_aggressiveness'] = max(0.0, min(5.0, new_agg))

    def _find_similar_situations(self, conditions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Hitta liknande situationer i prestandahistoriken."""
        if not self.performance_history:
            return []
        
        current_mode = conditions.get('mode', 'unknown')
        similar = []
        
        for record in self.performance_history:
            if record['mode'] == current_mode:
                similar.append(record)
        
        return similar[-20:]  # Senaste 20 liknande situationerna

    def _calculate_prediction_accuracy(self) -> float:
        """Beräkna noggrannheten för temperaturprediktioner."""
        if len(self.learning_sessions) < 10:
            return 0.5  # Neutral när vi har för lite data
        
        accuracies = []
        for session in self.learning_sessions[-20:]:
            if session.get('analysis', {}).get('prediction_accuracy'):
                accuracies.append(session['analysis']['prediction_accuracy'])
        
        return statistics.mean(accuracies) if accuracies else 0.5

    def _calculate_prediction_confidence(self, conditions: Dict[str, Any]) -> float:
        """Beräkna konfidensen för en predikt baserat på tillgänglig data."""
        similar_count = len(self._find_similar_situations(conditions))
        
        if similar_count >= 10:
            return 0.9
        elif similar_count >= 5:
            return 0.7
        elif similar_count >= 2:
            return 0.5
        else:
            return 0.3

    def _generate_situational_advice(self, conditions: Dict[str, Any], 
                                   predicted_temp: float, adaptive_agg: float) -> List[str]:
        """Generera situationsspecifika råd."""
        advice = []
        
        mode = conditions.get('mode', 'normal')
        current_agg = conditions.get('aggressiveness', 0)
        
        if abs(adaptive_agg - current_agg) > 0.5:
            if adaptive_agg > current_agg:
                advice.append(f"Överväg att öka aggressiviteten till {adaptive_agg:.1f} för bättre prestanda")
            else:
                advice.append(f"Du kan sänka aggressiviteten till {adaptive_agg:.1f} för energibesparing")
        
        if mode == 'heating' and adaptive_agg < 2.0:
            advice.append("Låg aggressivitet under uppvärmning kan förlänga tiden till måltemperatur")
        
        if mode == 'preboost':
            advice.append("Pre-boost aktiverat - systemet lär sig optimala förboost-strategier")
        
        return advice

    def _generate_next_steps(self) -> List[str]:
        """Generera förslag på nästa steg för optimering."""
        steps = []
        
        if len(self.learning_sessions) < 20:
            steps.append("Fortsätt samla data - behöver fler sessioner för bättre prediktioner")
        
        if len(self.performance_history) >= 50:
            steps.append("Tillräckligt med data för avancerade optimeringar")
        
        avg_success = 0
        if self.performance_history:
            recent_scores = [p['success_score'] for p in list(self.performance_history)[-10:]]
            avg_success = statistics.mean(recent_scores) if recent_scores else 0
        
        if avg_success < 0.6:
            steps.append("Prestandan kan förbättras - överväg att justera inställningar")
        elif avg_success > 0.8:
            steps.append("Utmärkt prestanda! Systemet fungerar optimalt")
        
        return steps

    def _get_model_statistics(self) -> Dict[str, Any]:
        """Hämta statistik om modellernas prestanda."""
        return {
            "temperature_model": {
                "trained": hasattr(self.temperature_model, 'is_trained') and self.temperature_model.is_trained,
                "training_samples": getattr(self.temperature_model, 'training_count', 0)
            },
            "efficiency_analyzer": {
                "active": len(self.performance_history) > 10,
                "data_points": len(self.performance_history)
            }
        }

    def get_status(self) -> Dict[str, Any]:
        """Hämta förbättrad status för ML-systemet."""
        base_status = {
            "collecting_data": True,
            "making_predictions": len(self.learning_sessions) >= 10,
            "adaptive_learning": len(self.performance_history) >= 20,
            "sessions_collected": len(self.learning_sessions),
            "performance_records": len(self.performance_history),
            "current_session_active": self.current_session is not None,
            "data_file": self.data_file,
            "model_version": "2.0"
        }
        
        # Lägg till ML-specifik status
        if len(self.learning_sessions) >= 5:
            base_status.update({
                "prediction_accuracy": self._calculate_prediction_accuracy(),
                "optimal_aggressiveness": self.adaptive_settings['optimal_aggressiveness'],
                "confidence_threshold": self.adaptive_settings['confidence_threshold']
            })
        
        return base_status


# === HJÄLPKLASSER FÖR ML-MODELLER ===

class SimpleTemperaturePredictor:
    """Enkel statistisk modell för temperaturprediktion."""
    
    def __init__(self):
        self.training_data = []
        self.is_trained = False
        self.training_count = 0
    
    def predict(self, conditions: Dict[str, Any]) -> float:
        """Förutsäg optimal temperatur."""
        if not self.is_trained or not self.training_data:
            # Fallback till enkel heuristik
            target_temp = conditions.get('target_temp', 20)
            indoor_temp = conditions.get('indoor_temp', 20)
            mode = conditions.get('mode', 'normal')
            
            if mode == 'heating':
                return target_temp - 2  # Lite lägre för att trigga uppvärmning
            elif mode == 'cooling':
                return target_temp + 2  # Lite högre för att trigga kylning
            else:
                return target_temp
        
        # Använd träningsdata för prediktion
        similar_results = []
        for data_point in self.training_data[-50:]:  # Senaste 50
            cond = data_point['conditions']
            if (abs(cond.get('target_temp', 20) - conditions.get('target_temp', 20)) < 2 and
                cond.get('mode') == conditions.get('mode')):
                similar_results.append(data_point['result'].get('predicted_optimal_temp', conditions.get('target_temp', 20)))
        
        if similar_results:
            return statistics.mean(similar_results)
        else:
            return conditions.get('target_temp', 20)
    
    def train(self, training_data: List[Dict[str, Any]]) -> None:
        """Träna modellen med historisk data."""
        self.training_data = training_data[-100:]  # Behåll senaste 100
        self.training_count = len(self.training_data)
        self.is_trained = len(self.training_data) >= 5
    
    def update(self, data_point: Dict[str, Any]) -> None:
        """Uppdatera modellen med en ny datapunkt."""
        self.training_data.append(data_point)
        if len(self.training_data) > 100:
            self.training_data = self.training_data[-100:]
        self.training_count += 1
        self.is_trained = len(self.training_data) >= 5


class EnergyEfficiencyAnalyzer:
    """Analyserar energieffektivitet för olika strategier."""
    
    def __init__(self):
        self.efficiency_data = defaultdict(list)
    
    def predict_consumption(self, mode: str, aggressiveness: float, duration_hours: float) -> float:
        """Förutsäg energiförbrukning (förenklad modell)."""
        base_consumption = 1.0  # kWh per timme baseline
        
        mode_multipliers = {
            'heating': 1.5,
            'cooling': 1.2,
            'preboost': 2.0,
            'braking_by_price': 0.3,
            'normal': 1.0
        }
        
        mode_mult = mode_multipliers.get(mode, 1.0)
        agg_mult = 1.0 + (aggressiveness * 0.2)  # 20% ökning per aggressivitetsnivå
        
        return base_consumption * mode_mult * agg_mult * duration_hours
    
    def analyze_efficiency_trends(self, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analysera effektivitetstrender från sessioner."""
        mode_efficiency = defaultdict(list)
        
        for session in sessions:
            if session.get('analysis') and session.get('initial'):
                mode = session['initial'].get('mode', 'unknown')
                efficiency = session['analysis'].get('energy_efficiency', 0)
                aggressiveness = session['initial'].get('aggressiveness', 0)
                
                mode_efficiency[mode].append({
                    'efficiency': efficiency,
                    'aggressiveness': aggressiveness,
                    'success_score': session['analysis'].get('success_score', 0)
                })
        
        # Beräkna trender per mode
        trends = {}
        for mode, data in mode_efficiency.items():
            if len(data) >= 3:
                efficiencies = [d['efficiency'] for d in data]
                trends[mode] = {
                    'avg_efficiency': statistics.mean(efficiencies),
                    'efficiency_trend': 'improving' if len(efficiencies) > 1 and efficiencies[-1] > efficiencies[0] else 'stable',
                    'sample_count': len(data),
                    'best_aggressiveness': self._find_best_aggressiveness_for_mode(data)
                }
        
        return {
            'mode_trends': trends,
            'overall_efficiency': statistics.mean([t['avg_efficiency'] for t in trends.values()]) if trends else 0,
            'most_efficient_mode': max(trends.keys(), key=lambda k: trends[k]['avg_efficiency']) if trends else 'unknown'
        }
    
    def _find_best_aggressiveness_for_mode(self, mode_data: List[Dict[str, Any]]) -> float:
        """Hitta bästa aggressivitetsnivå för en specifik mode."""
        if len(mode_data) < 3:
            return 3.0  # Default
        
        # Sortera efter success_score och ta genomsnittet av de bästa
        sorted_data = sorted(mode_data, key=lambda x: x['success_score'], reverse=True)
        top_performers = sorted_data[:max(3, len(sorted_data)//3)]
        
        return statistics.mean([d['aggressiveness'] for d in top_performers])
    
    def update(self, session: Dict[str, Any]) -> None:
        """Uppdatera med ny sessiondata."""
        if session.get('analysis') and session.get('initial'):
            mode = session['initial'].get('mode', 'unknown')
            efficiency = session['analysis'].get('energy_efficiency', 0)
            self.efficiency_data[mode].append(efficiency)
            
            # Begränsa historik per mode
            if len(self.efficiency_data[mode]) > 50:
                self.efficiency_data[mode] = self.efficiency_data[mode][-50:]


class RecommendationEngine:
    """Motor för att generera rekommendationer baserat på ML-analys."""
    
    def __init__(self):
        self.recommendation_history = []
    
    def generate_recommendations(self, performance_history: deque, adaptive_settings: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generera rekommendationer baserat på prestanda och inställningar."""
        recommendations = []
        
        if len(performance_history) < 10:
            recommendations.append({
                'type': 'data_collection',
                'priority': 'high',
                'title': 'Samla mer data',
                'description': 'Behöver fler sessioner för att ge meningsfulla rekommendationer',
                'action': 'Låt systemet köra i några dagar till'
            })
            return recommendations
        
        # Analysera recent prestanda
        recent_performance = list(performance_history)[-20:]
        avg_success = statistics.mean([p['success_score'] for p in recent_performance])
        success_trend = self._calculate_trend([p['success_score'] for p in recent_performance])
        
        # Rekommendationer baserat på prestanda
        if avg_success < 0.5:
            recommendations.append({
                'type': 'performance',
                'priority': 'high',
                'title': 'Låg prestanda upptäckt',
                'description': f'Genomsnittlig framgång är {avg_success*100:.1f}%. Rekommenderar justering av inställningar.',
                'action': f'Överväg att ändra aggressivitet från {adaptive_settings["optimal_aggressiveness"]:.1f} till {self._suggest_aggressiveness_adjustment(recent_performance):.1f}'
            })
        
        if success_trend < -0.1:
            recommendations.append({
                'type': 'trend',
                'priority': 'medium',
                'title': 'Negativ prestandatrend',
                'description': 'Prestandan har försämrats över tid',
                'action': 'Kontrollera om externa förhållanden har förändrats'
            })
        
        # Energieffektivitetsrekommendationer
        energy_recommendations = self._analyze_energy_efficiency(recent_performance)
        recommendations.extend(energy_recommendations)
        
        # Mode-specifika rekommendationer
        mode_recommendations = self._analyze_mode_performance(recent_performance)
        recommendations.extend(mode_recommendations)
        
        # Säsongsrekommendationer
        seasonal_recommendations = self._generate_seasonal_recommendations()
        recommendations.extend(seasonal_recommendations)
        
        # Sortera efter prioritet
        priority_order = {'high': 3, 'medium': 2, 'low': 1}
        recommendations.sort(key=lambda x: priority_order.get(x['priority'], 0), reverse=True)
        
        return recommendations[:5]  # Returnera topp 5 rekommendationer
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Beräkna trend i en värdeserie (positiv = förbättring)."""
        if len(values) < 3:
            return 0.0
        
        # Enkel linjär regression slope
        n = len(values)
        x = list(range(n))
        
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(xi * yi for xi, yi in zip(x, values))
        sum_x2 = sum(xi * xi for xi in x)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0
        return slope
    
    def _suggest_aggressiveness_adjustment(self, performance_data: List[Dict[str, Any]]) -> float:
        """Föreslå justering av aggressivitet baserat på prestanda."""
        # Gruppera efter aggressivitet och hitta bästa prestanda
        agg_performance = defaultdict(list)
        
        for p in performance_data:
            agg = p.get('aggressiveness', 3.0)
            success = p.get('success_score', 0)
            agg_performance[round(agg * 2) / 2].append(success)  # Rundad till 0.5
        
        # Hitta aggressivitet med bäst genomsnittsprestanda
        best_agg = 3.0
        best_score = 0
        
        for agg, scores in agg_performance.items():
            if len(scores) >= 2:  # Behöver minst 2 samples
                avg_score = statistics.mean(scores)
                if avg_score > best_score:
                    best_score = avg_score
                    best_agg = agg
        
        return max(0.0, min(5.0, best_agg))
    
    def _analyze_energy_efficiency(self, performance_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analysera energieffektivitet och generera rekommendationer."""
        recommendations = []
        
        # Hitta modes med låg energieffektivitet
        mode_efficiency = defaultdict(list)
        for p in performance_data:
            mode = p.get('mode', 'unknown')
            # Estimerad energieffektivitet baserat på aggressivitet och mode
            agg = p.get('aggressiveness', 0)
            if mode in ['heating', 'cooling']:
                efficiency = max(0, 1 - agg * 0.15)  # Högre aggressivitet = lägre effektivitet
            else:
                efficiency = 0.8  # Neutral effektivitet för andra modes
                
            mode_efficiency[mode].append(efficiency)
        
        for mode, efficiencies in mode_efficiency.items():
            if len(efficiencies) >= 3:
                avg_efficiency = statistics.mean(efficiencies)
                if avg_efficiency < 0.6 and mode in ['heating', 'cooling']:
                    recommendations.append({
                        'type': 'energy',
                        'priority': 'medium',
                        'title': f'Låg energieffektivitet i {mode}-läge',
                        'description': f'Genomsnittlig effektivitet: {avg_efficiency*100:.1f}%',
                        'action': f'Överväg att sänka aggressiviteten för {mode}-operationer'
                    })
        
        return recommendations
    
    def _analyze_mode_performance(self, performance_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analysera prestanda per mode och generera rekommendationer."""
        recommendations = []
        
        mode_performance = defaultdict(list)
        for p in performance_data:
            mode = p.get('mode', 'unknown')
            success = p.get('success_score', 0)
            mode_performance[mode].append(success)
        
        for mode, scores in mode_performance.items():
            if len(scores) >= 3:
                avg_score = statistics.mean(scores)
                if avg_score < 0.4:
                    if mode == 'heating':
                        recommendations.append({
                            'type': 'mode_specific',
                            'priority': 'high',
                            'title': 'Uppvärmning fungerar dåligt',
                            'description': f'Framgång i heating-läge: {avg_score*100:.1f}%',
                            'action': 'Kontrollera värmepumpens inställningar och eventuella blockeringar'
                        })
                    elif mode == 'preboost':
                        recommendations.append({
                            'type': 'mode_specific',
                            'priority': 'medium',
                            'title': 'Pre-boost kan förbättras',
                            'description': f'Pre-boost framgång: {avg_score*100:.1f}%',
                            'action': 'Justera pre-boost timing eller trösklar'
                        })
        
        return recommendations
    
    def _generate_seasonal_recommendations(self) -> List[Dict[str, Any]]:
        """Generera säsongsbaserade rekommendationer."""
        recommendations = []
        current_month = datetime.now().month
        
        if current_month in [12, 1, 2]:  # Vinter
            recommendations.append({
                'type': 'seasonal',
                'priority': 'low',
                'title': 'Vinteroptimering',
                'description': 'Vinterperiod - fokusera på energieffektiv uppvärmning',
                'action': 'Överväg att öka pre-boost-aggressivitet under kalla perioder'
            })
        elif current_month in [6, 7, 8]:  # Sommar
            recommendations.append({
                'type': 'seasonal',
                'priority': 'low',
                'title': 'Sommaroptimering',
                'description': 'Sommarperiod - minimal uppvärmning behövs',
                'action': 'Kontrollera att sommartröskeln är korrekt inställd'
            })
        
        return recommendations
