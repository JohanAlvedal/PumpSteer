# ml_config_helper.py
# Hjälpklasser för ML-konfiguration och tjänster i PumpSteer

import logging
from typing import Dict, Any, List, Optional
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import service
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

# Service schemas för ML-funktioner
ML_GET_INSIGHTS_SCHEMA = vol.Schema({})

ML_GET_RECOMMENDATIONS_SCHEMA = vol.Schema({
    vol.Optional('priority_filter'): vol.In(['high', 'medium', 'low']),
    vol.Optional('max_results', default=5): vol.Range(min=1, max=20)
})

ML_GET_ADVICE_SCHEMA = vol.Schema({
    vol.Optional('indoor_temp'): vol.Coerce(float),
    vol.Optional('outdoor_temp'): vol.Coerce(float),
    vol.Optional('target_temp'): vol.Coerce(float),
    vol.Optional('aggressiveness'): vol.Range(min=0.0, max=5.0),
    vol.Optional('mode'): vol.In(['normal', 'heating', 'cooling', 'preboost', 'summer_mode'])
})

ML_TOGGLE_ADAPTIVE_SCHEMA = vol.Schema({
    vol.Optional('enable'): vol.Coerce(bool)
})

ML_RESET_LEARNING_SCHEMA = vol.Schema({
    vol.Optional('confirm', default=False): vol.Coerce(bool),
    vol.Optional('keep_insights', default=True): vol.Coerce(bool)
})

class PumpSteerMLServices:
    """Hanterar ML-relaterade tjänster för PumpSteer."""
    
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._sensors = {}  # Registry av PumpSteer-sensorer
    
    def register_sensor(self, entity_id: str, sensor_instance) -> None:
        """Registrera en PumpSteer-sensor för ML-tjänster."""
        self._sensors[entity_id] = sensor_instance
        _LOGGER.debug(f"Registered PumpSteer sensor for ML services: {entity_id}")
    
    def unregister_sensor(self, entity_id: str) -> None:
        """Avregistrera en PumpSteer-sensor."""
        self._sensors.pop(entity_id, None)
        _LOGGER.debug(f"Unregistered PumpSteer sensor: {entity_id}")
    
    async def async_setup_services(self) -> None:
        """Sätt upp ML-tjänster."""
        try:
            # Tjänst för att hämta ML-insikter
            self.hass.services.async_register(
                'pumpsteer',
                'get_ml_insights',
                self._handle_get_ml_insights,
                schema=ML_GET_INSIGHTS_SCHEMA
            )
            
            # Tjänst för att hämta rekommendationer
            self.hass.services.async_register(
                'pumpsteer',
                'get_ml_recommendations',
                self._handle_get_ml_recommendations,
                schema=ML_GET_RECOMMENDATIONS_SCHEMA
            )
            
            # Tjänst för situationsspecifika råd
            self.hass.services.async_register(
                'pumpsteer',
                'get_situation_advice',
                self._handle_get_situation_advice,
                schema=ML_GET_ADVICE_SCHEMA
            )
            
            # Tjänst för att växla adaptivt läge
            self.hass.services.async_register(
                'pumpsteer',
                'toggle_adaptive_mode',
                self._handle_toggle_adaptive_mode,
                schema=ML_TOGGLE_ADAPTIVE_SCHEMA
            )
            
            # Tjänst för att återställa ML-inlärning
            self.hass.services.async_register(
                'pumpsteer',
                'reset_ml_learning',
                self._handle_reset_ml_learning,
                schema=ML_RESET_LEARNING_SCHEMA
            )
            
            _LOGGER.info("PumpSteer ML services registered successfully")
            
        except Exception as e:
            _LOGGER.error(f"Failed to setup ML services: {e}")
    
    async def async_remove_services(self) -> None:
        """Ta bort ML-tjänster."""
        services_to_remove = [
            'get_ml_insights',
            'get_ml_recommendations', 
            'get_situation_advice',
            'toggle_adaptive_mode',
            'reset_ml_learning'
        ]
        
        for service_name in services_to_remove:
            if self.hass.services.has_service('pumpsteer', service_name):
                self.hass.services.async_remove('pumpsteer', service_name)
        
        _LOGGER.info("PumpSteer ML services removed")
    
    def _get_primary_sensor(self):
        """Hämta den primära PumpSteer-sensorn."""
        if not self._sensors:
            return None
        return next(iter(self._sensors.values()))
    
    async def _handle_get_ml_insights(self, call: ServiceCall) -> None:
        """Hantera get_ml_insights tjänst."""
        sensor = self._get_primary_sensor()
        if not sensor:
            _LOGGER.error("No PumpSteer sensor found for ML insights")
            return
        
        try:
            insights = sensor.get_enhanced_ml_insights()
            
            # Logga insikter för användaren
            _LOGGER.info("=== PumpSteer ML Insights ===")
            _LOGGER.info(f"Status: {insights.get('status', 'unknown')}")
            
            if 'overall_performance' in insights:
                perf = insights['overall_performance']
                _LOGGER.info(f"Success Rate: {perf.get('success_rate', 0):.1f}%")
                _LOGGER.info(f"Prediction Accuracy: {perf.get('prediction_accuracy', 0):.1f}%")
            
            if 'recommendations' in insights:
                recs = insights['recommendations'][:3]  # Topp 3
                _LOGGER.info("Top Recommendations:")
                for i, rec in enumerate(recs, 1):
                    _LOGGER.info(f"  {i}. {rec.get('title', 'Unknown')} (Priority: {rec.get('priority', 'unknown')})")
            
            # Spara till sensor attribut för UI-visning
            if hasattr(sensor, '_attributes'):
                sensor._attributes['Last_ML_Insights'] = {
                    'timestamp': insights.get('timestamp', 'unknown'),
                    'status': insights.get('status', 'unknown'),
                    'success_rate': insights.get('overall_performance', {}).get('success_rate', 0)
                }
            
        except Exception as e:
            _LOGGER.error(f"Error getting ML insights: {e}")
    
    async def _handle_get_ml_recommendations(self, call: ServiceCall) -> None:
        """Hantera get_ml_recommendations tjänst."""
        sensor = self._get_primary_sensor()
        if not sensor:
            _LOGGER.error("No PumpSteer sensor found for ML recommendations")
            return
        
        try:
            priority_filter = call.data.get('priority_filter')
            max_results = call.data.get('max_results', 5)
            
            recommendations = sensor.get_ml_recommendations()
            
            # Filtrera efter prioritet om angivet
            if priority_filter:
                recommendations = [r for r in recommendations if r.get('priority') == priority_filter]
            
            # Begränsa antal resultat
            recommendations = recommendations[:max_results]
            
            # Logga rekommendationer
            _LOGGER.info("=== PumpSteer ML Recommendations ===")
            if not recommendations:
                _LOGGER.info("No recommendations available")
            else:
                for i, rec in enumerate(recommendations, 1):
                    _LOGGER.info(f"{i}. [{rec.get('priority', 'unknown').upper()}] {rec.get('title', 'Unknown')}")
                    _LOGGER.info(f"   Action: {rec.get('action', 'No action specified')}")
            
        except Exception as e:
            _LOGGER.error(f"Error getting ML recommendations: {e}")
    
    async def _handle_get_situation_advice(self, call: ServiceCall) -> None:
        """Hantera get_situation_advice tjänst."""
        sensor = self._get_primary_sensor()
        if not sensor:
            _LOGGER.error("No PumpSteer sensor found for situation advice")
            return
        
        try:
            # Bygg conditions från call data eller använd aktuella
            conditions = {}
            for key in ['indoor_temp', 'outdoor_temp', 'target_temp', 'aggressiveness', 'mode']:
                if key in call.data:
                    conditions[key] = call.data[key]
            
            advice = sensor.get_situation_specific_advice(conditions if conditions else None)
            
            # Logga råd
            _LOGGER.info("=== PumpSteer Situation-Specific Advice ===")
            _LOGGER.info(f"Predicted Optimal Temperature: {advice.get('predicted_optimal_temperature', 'N/A')}°C")
            _LOGGER.info(f"Recommended Aggressiveness: {advice.get('recommended_aggressiveness', 'N/A')}")
            _LOGGER.info(f"Prediction Confidence: {advice.get('confidence', 0)*100:.0f}%")
            
            ml_advice = advice.get('advice', [])
            if ml_advice:
                _LOGGER.info("Advice:")
                for i, tip in enumerate(ml_advice, 1):
                    _LOGGER.info(f"  {i}. {tip}")
            
        except Exception as e:
            _LOGGER.error(f"Error getting situation advice: {e}")
    
    async def _handle_toggle_adaptive_mode(self, call: ServiceCall) -> None:
        """Hantera toggle_adaptive_mode tjänst."""
        sensor = self._get_primary_sensor()
        if not sensor:
            _LOGGER.error("No PumpSteer sensor found for adaptive mode toggle")
            return
        
        try:
            enable = call.data.get('enable')
            result = sensor.toggle_adaptive_mode(enable)
            
            _LOGGER.info(f"PumpSteer Adaptive Mode: {result.get('message', 'Status unknown')}")
            
        except Exception as e:
            _LOGGER.error(f"Error toggling adaptive mode: {e}")
    
    async def _handle_reset_ml_learning(self, call: ServiceCall) -> None:
        """Hantera reset_ml_learning tjänst."""
        sensor = self._get_primary_sensor()
        if not sensor:
            _LOGGER.error("No PumpSteer sensor found for ML reset")
            return
        
        confirm = call.data.get('confirm', False)
        if not confirm:
            _LOGGER.warning("ML learning reset requires 'confirm: true' parameter")
            return
        
        try:
            keep_insights = call.data.get('keep_insights', True)
            
            if hasattr(sensor, 'ml_collector') and sensor.ml_collector:
                # Implementera reset-logik
                if keep_insights:
                    # Behåll insikter men rensa sessiondata
                    sensor.ml_collector.learning_sessions = []
                    _LOGGER.info("PumpSteer ML: Session data cleared, insights preserved")
                else:
                    # Fullständig återställning
                    sensor.ml_collector.learning_sessions = []
                    sensor.ml_collector.performance_history.clear()
                    sensor.ml_collector.adaptive_settings = {
                        'optimal_aggressiveness': 3.0,
                        'learning_rate': 0.1,
                        'confidence_threshold': 0.7,
                        'min_samples_for_prediction': 10
                    }
                    _LOGGER.info("PumpSteer ML: Complete learning data reset")
                
                # Spara ändringar
                await sensor.ml_collector.async_save_data()
            else:
                _LOGGER.warning("No ML collector available for reset")
        
        except Exception as e:
            _LOGGER.error(f"Error resetting ML learning: {e}")


class MLConfigurationValidator:
    """Validerar ML-konfiguration och inställningar."""
    
    @staticmethod
    def validate_ml_settings(settings: Dict[str, Any]) -> List[str]:
        """Validera ML-inställningar och returnera eventuella fel."""
        errors = []
        
        # Kontrollera obligatoriska inställningar
        required_settings = ['optimal_aggressiveness', 'learning_rate', 'confidence_threshold']
        for setting in required_settings:
            if setting not in settings:
                errors.append(f"Missing required ML setting: {setting}")
        
        # Validera värdeintervall
        if 'optimal_aggressiveness' in settings:
            agg = settings['optimal_aggressiveness']
            if not (0.0 <= agg <= 5.0):
                errors.append(f"optimal_aggressiveness must be 0.0-5.0, got {agg}")
        
        if 'learning_rate' in settings:
            lr = settings['learning_rate']
            if not (0.001 <= lr <= 1.0):
                errors.append(f"learning_rate must be 0.001-1.0, got {lr}")
        
        if 'confidence_threshold' in settings:
            ct = settings['confidence_threshold']
            if not (0.1 <= ct <= 1.0):
                errors.append(f"confidence_threshold must be 0.1-1.0, got {ct}")
        
        return errors
    
    @staticmethod
    def get_default_ml_settings() -> Dict[str, Any]:
        """Hämta standardinställningar för ML."""
        return {
            'optimal_aggressiveness': 3.0,
            'learning_rate': 0.1,
            'confidence_threshold': 0.7,
            'min_samples_for_prediction': 10,
            'max_training_samples': 100,
            'performance_history_size': 1000,
            'enable_adaptive_mode': True,
            'enable_predictions': True,
            'auto_adjust_aggressiveness': True
        }
    
    @staticmethod
    def upgrade_ml_settings(old_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Uppgradera gamla ML-inställningar till ny version."""
        defaults = MLConfigurationValidator.get_default_ml_settings()
        
        # Starta med standardvärden
        new_settings = defaults.copy()
        
        # Behåll kompatibla gamla värden
        compatible_keys = [
            'optimal_aggressiveness', 'learning_rate', 'confidence_threshold',
            'min_samples_for_prediction'
        ]
        
        for key in compatible_keys:
            if key in old_settings:
                new_settings[key] = old_settings[key]
        
        return new_settings


def setup_ml_automation_suggestions() -> List[Dict[str, Any]]:
    """Generera förslag på automationer för ML-funktionalitet."""
    return [
        {
            'name': 'PumpSteer ML Daily Report',
            'description': 'Daglig rapport av ML-prestanda och rekommendationer',
            'trigger': {
                'platform': 'time',
                'at': '07:00:00'
            },
            'action': {
                'service': 'pumpsteer.get_ml_insights'
            }
        },
        {
            'name': 'PumpSteer ML Weekly Recommendations',
            'description': 'Veckovis rekommendationsrapport',
            'trigger': {
                'platform': 'time',
                'at': '08:00:00',
                'weekday': ['mon']
            },
            'action': {
                'service': 'pumpsteer.get_ml_recommendations',
                'data': {
                    'priority_filter': 'high',
                    'max_results': 3
                }
            }
        },
        {
            'name': 'PumpSteer Adaptive Mode Monitor',
            'description': 'Övervaka när adaptivt läge gör justeringar',
            'trigger': {
                'platform': 'state',
                'entity_id': 'sensor.pumpsteer',
                'attribute': 'ML Adjusted'
            },
            'condition': {
                'condition': 'template',
                'value_template': "{{ trigger.to_state.attributes['ML Adjusted'] == true }}"
            },
            'action': {
                'service': 'persistent_notification.create',
                'data': {
                    'title': 'PumpSteer ML Adjustment',
                    'message': 'Adaptive mode adjusted aggressiveness based on learning'
                }
            }
        }
    ]
