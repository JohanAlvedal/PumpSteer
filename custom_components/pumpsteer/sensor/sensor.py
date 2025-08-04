# sensor.py - Städad version med enkel ML

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

# Importera befintliga moduler
from ..pre_boost import check_combined_preboost
from ..holiday import is_holiday_mode_active, HOLIDAY_TARGET_TEMPERATURE
from ..temp_control_logic import calculate_temperature_output
from ..electricity_price import async_hybrid_classify_with_history, classify_prices
from ..ml_adaptive import PumpSteerMLCollector
from ..settings import (
    DEFAULT_HOUSE_INERTIA,
    HOLIDAY_TEMP,
    BRAKING_MODE_TEMP,
    PREBOOST_MAX_OUTDOOR_TEMP,
    AGGRESSIVENESS_SCALING_FACTOR,
    PREBOOST_OUTPUT_TEMP
)
from ..utils import (
    safe_float, get_state, get_attr,
    safe_get_price_data, safe_parse_temperature_forecast,
    validate_required_entities, safe_get_entity_state_with_description,
    safe_array_slice
)

_LOGGER = logging.getLogger(__name__)

# Enkel ML-import
try:
    from .ml_adaptive import PumpSteerMLCollector
    ML_AVAILABLE = True
    _LOGGER.info("ML features available")
except ImportError as e:
    ML_AVAILABLE = False
    _LOGGER.info(f"ML features disabled: {e}")

DOMAIN = "pumpsteer"

# Hardcoded entities
HARDCODED_ENTITIES = {
    "target_temp_entity": "input_number.indoor_target_temperature",
    "summer_threshold_entity": "input_number.pumpsteer_summer_threshold",
    "holiday_mode_boolean_entity": "input_boolean.holiday_mode",
    "holiday_start_datetime_entity": "input_datetime.holiday_start",
    "holiday_end_datetime_entity": "input_datetime.holiday_end",
    "hourly_forecast_temperatures_entity": "input_text.hourly_forecast_temperatures",
    "aggressiveness_entity": "input_number.pumpsteer_aggressiveness",
    "house_inertia_entity": "input_number.house_inertia",
    "price_model_entity": "input_select.pumpsteer_price_model"
}

NEUTRAL_TEMP_THRESHOLD = 0.5
DEFAULT_SUMMER_THRESHOLD = 18.0
DEFAULT_AGGRESSIVENESS = 3.0

def safe_get_current_price_and_category(
    prices: List[float],
    categories: List[str],
    hour: int,
    mode: str = "unknown"
) -> Tuple[float, str]:
    """Säkert hämta aktuellt pris och kategori för given timme."""
    if not prices or hour >= len(prices) or hour < 0:
        _LOGGER.warning(f"Invalid price data access: hour={hour}, prices_len={len(prices) if prices else 0}")
        return 0.0, "unknown"

    current_price = prices[hour]

    if not categories or hour >= len(categories):
        _LOGGER.warning(f"Invalid category data access: hour={hour}, categories_len={len(categories) if categories else 0}")
        price_category = "unknown"
    else:
        price_category = f"{categories[hour]} ({mode})"

    return current_price, price_category

class PumpSteerSensor(Entity):
    """PumpSteer sensor för värmepumpskontroll."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialisera PumpSteer-sensorn."""
        self.hass = hass
        self._config_entry = config_entry
        self._state = None
        self._attributes = {}
        self._name = "PumpSteer"
        self._last_update_time = None

        self._attr_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"
        self._attr_state_class = "measurement"
        self._attr_unique_id = config_entry.entry_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="Custom",
            model="Heat Pump Controller",
            sw_version="1.2.0"
        )

        # Enkel ML-initialisering
        self.ml_collector = None
        self._ml_session_started = False
        self._ml_session_start_mode = None
        self._last_price_category = "unknown"

        if ML_AVAILABLE:
            try:
                self.ml_collector = PumpSteerMLCollector(hass)
                _LOGGER.info("PumpSteer: ML system enabled")
            except Exception as e:
                _LOGGER.warning(f"PumpSteer: ML initialization failed: {e}")
                self.ml_collector = None
        else:
            _LOGGER.info("PumpSteer: Running without ML features")

        config_entry.add_update_listener(self.async_options_update_listener)
        _LOGGER.debug("PumpSteerSensor: Initialization complete")

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    @property
    def state(self) -> StateType:
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._attributes,
            "friendly_name": "PumpSteer"
        }

    @property
    def unit_of_measurement(self) -> str:
        return self._attr_unit_of_measurement

    @property
    def device_class(self) -> str:
        return self._attr_device_class

    @property
    def icon(self) -> str:
        return "mdi:thermostat-box"

    @property
    def available(self) -> bool:
        return self._state != STATE_UNAVAILABLE

    @property
    def should_poll(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        """Kallas när entiteten läggs till i Home Assistant."""
        if self.ml_collector and hasattr(self.ml_collector, 'async_load_data'):
            try:
                await self.ml_collector.async_load_data()
                _LOGGER.debug("ML data loaded successfully")
            except Exception as e:
                _LOGGER.error(f"Failed to load ML data: {e}")
                self.ml_collector = None
        
        await super().async_added_to_hass()

    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._config_entry = entry
        await self.async_update()

    def _get_sensor_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Hämta sensordata från Home Assistant."""
        return {
            'indoor_temp': safe_float(get_state(self.hass, config.get("indoor_temp_entity"))),
            'outdoor_temp': safe_float(get_state(self.hass, config.get("real_outdoor_entity"))),
            'target_temp': safe_float(get_state(self.hass, HARDCODED_ENTITIES["target_temp_entity"])),
            'summer_threshold': safe_float(get_state(self.hass, HARDCODED_ENTITIES["summer_threshold_entity"])) or DEFAULT_SUMMER_THRESHOLD,
            'aggressiveness': safe_float(get_state(self.hass, HARDCODED_ENTITIES["aggressiveness_entity"])) or DEFAULT_AGGRESSIVENESS,
            'inertia': safe_float(get_state(self.hass, HARDCODED_ENTITIES["house_inertia_entity"])) or DEFAULT_HOUSE_INERTIA,
            'outdoor_temp_forecast_entity': HARDCODED_ENTITIES["hourly_forecast_temperatures_entity"]
        }

    def _validate_required_data(self, sensor_data: Dict[str, Any], prices: List[float]) -> Optional[List[str]]:
        """Validera att all nödvändig data finns tillgänglig."""
        missing = []

        if sensor_data['indoor_temp'] is None:
            missing.append("Indoor temperature")
        if sensor_data['outdoor_temp'] is None:
            missing.append("Outdoor temperature")
        if sensor_data['target_temp'] is None:
            missing.append("Target temperature")
        if not prices:
            missing.append("Electricity prices")
        if sensor_data['outdoor_temp_forecast_entity'] and get_state(self.hass, sensor_data['outdoor_temp_forecast_entity']) is None:
            missing.append("Outdoor temperature forecast entity data not available")
        elif not sensor_data['outdoor_temp_forecast_entity']:
            _LOGGER.debug("Outdoor temperature forecast entity not configured, skipping pre-boost temperature forecast check.")

        return missing if missing else None

    def _calculate_output_temperature(
        self,
        sensor_data: Dict[str, Any],
        prices: List[float],
        price_category: str,
        now_hour: int
    ) -> Tuple[float, str]:
        """Beräkna uttemperatur baserat på aktuella förhållanden."""
        indoor_temp = sensor_data['indoor_temp']
        outdoor_temp = sensor_data['outdoor_temp']
        target_temp = sensor_data['target_temp']
        summer_threshold = sensor_data['summer_threshold']
        aggressiveness = sensor_data['aggressiveness']
        inertia = sensor_data['inertia']
        outdoor_temp_forecast_entity = sensor_data['outdoor_temp_forecast_entity']

        preboost_mode = None
        temp_forecast_csv = None

        if outdoor_temp < PREBOOST_MAX_OUTDOOR_TEMP:
            if outdoor_temp_forecast_entity:
                temp_forecast_csv = get_state(self.hass, outdoor_temp_forecast_entity)

            if temp_forecast_csv:
                try:
                    preboost_mode = check_combined_preboost(
                        temp_csv=temp_forecast_csv,
                        prices=prices,
                        cold_threshold=target_temp - 2.0,
                        aggressiveness=aggressiveness,
                        inertia=inertia
                    )
                except Exception as e:
                    _LOGGER.error(f"Error in pre-boost check: {e}")
                    preboost_mode = None
            else:
                _LOGGER.debug("No temperature forecast available for pre-boost check.")

        if preboost_mode == "preboost":
            _LOGGER.info(f"Pre-boost activated. Setting fake temp to {PREBOOST_OUTPUT_TEMP} °C")
            return PREBOOST_OUTPUT_TEMP, "preboost"

        if outdoor_temp >= summer_threshold:
            return outdoor_temp, "summer_mode"

        if "expensive" in price_category or "very_expensive" in price_category:
            _LOGGER.info(f"Blocking heating at hour {now_hour} due to {price_category} price (setting fake temp to {BRAKING_MODE_TEMP} °C)")
            return BRAKING_MODE_TEMP, "braking_by_price"

        temp_diff = indoor_temp - target_temp

        if abs(temp_diff) <= NEUTRAL_TEMP_THRESHOLD:
            return outdoor_temp, "neutral"

        try:
            fake_temp, mode = calculate_temperature_output(
                indoor_temp,
                target_temp,
                outdoor_temp,
                aggressiveness
            )
            
        
            current_error = target_temp - indoor_temp
            dt_hours = 1  # Gissar att sensorn körs timvis, ändra annars
            delta = current_error * dt_hours
        
            prev_integral = safe_float(get_state(self.hass, "input_number.integral_temp_error")) or 0.0
            new_integral = prev_integral + delta
            new_integral = max(-1000, min(1000, new_integral))  # Begränsa
        
            # Skriv tillbaka till Home Assistant
            self.hass.services.call(
                "input_number", "set_value",
                {"entity_id": "input_number.integral_temp_error", "value": round(new_integral, 2)},
                blocking=False
            )
        
            gain = safe_float(get_state(self.hass, "input_number.pumpsteer_integral_gain")) or 0.0
            if gain > 0:
                adjustment = gain * new_integral
                fake_temp += adjustment
                _LOGGER.debug(f"Integral control: error={current_error:.2f}, sum={new_integral:.2f}, gain={gain:.2f}, adj={adjustment:.2f}")
        except Exception as e:
            _LOGGER.warning(f"Integral logic failed: {e}")

            return fake_temp, mode
        except Exception as e:
            _LOGGER.error(f"Error in temperature calculation: {e}")
            return outdoor_temp, "error"

    def _collect_ml_data(self, sensor_data: Dict[str, Any], mode: str, fake_temp: float) -> None:
        """Samla data för maskininlärning."""
        if not self.ml_collector:
            return

        try:
            ml_data = {
                "indoor_temp": sensor_data.get('indoor_temp'),
                "outdoor_temp": sensor_data.get('outdoor_temp'),
                "target_temp": sensor_data.get('target_temp'),
                "aggressiveness": sensor_data.get('aggressiveness', 0),
                "inertia": sensor_data.get('inertia'),
                "mode": mode,
                "fake_temp": fake_temp,
                "price_category": self._last_price_category,
                "timestamp": dt_util.now().isoformat()
            }

            if not self._ml_session_started:
                self.ml_collector.start_session(ml_data)
                self._ml_session_started = True
                self._ml_session_start_mode = mode

            self.ml_collector.update_session(ml_data)

            if (self._ml_session_start_mode != mode and mode in ['neutral', 'summer_mode']):
                self.ml_collector.end_session("mode_change", ml_data)
                self._ml_session_started = False

        except Exception as e:
            _LOGGER.debug(f"ML data collection error (non-critical): {e}")

    async def _get_price_data(
        self,
        config: Dict[str, Any],
        now_hour: int
    ) -> Tuple[List[float], float, str, List[str]]:
        """Hämta prisdata och klassificera priser."""
        entity_id = config.get("electricity_price_entity")

        if not entity_id:
            _LOGGER.error("No electricity price entity configured")
            return [], 0.0, "unknown", []

        prices_raw = get_attr(self.hass, entity_id, "today") or get_attr(self.hass, entity_id, "raw_today")
        if not prices_raw:
            _LOGGER.warning(f"Could not retrieve electricity prices from {entity_id}")
            return [], 0.0, "unknown", []

        try:
            prices = [float(p) for p in prices_raw if isinstance(p, (float, int)) and p is not None]
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Error converting prices to float: {e}")
            return [], 0.0, "unknown", []

        if not prices:
            _LOGGER.warning("No valid prices found after conversion")
            return [], 0.0, "unknown", []

        mode = get_state(self.hass, HARDCODED_ENTITIES["price_model_entity"]) or "hybrid"
        categories = []

        try:
            if mode == "percentiles":
                categories = classify_prices(prices)
            else:
                categories = await async_hybrid_classify_with_history(
                    self.hass,
                    price_list=prices,
                    price_entity_id=entity_id,
                    trailing_hours=72
                )
        except Exception as e:
            _LOGGER.error(f"Error classifying prices: {e}")
            categories = ["unknown"] * len(prices)

        current_price, price_category = safe_get_current_price_and_category(
            prices, categories, now_hour, mode
        )

        return prices, current_price, price_category, categories

    def _build_attributes(
        self,
        sensor_data: Dict[str, Any],
        prices: List[float],
        current_price: float,
        price_category: str,
        mode: str,
        holiday: bool,
        categories: List[str],
        now_hour: int
    ) -> Dict[str, Any]:
        """Bygg attribut-dictionary för sensorn."""
        max_price = max(prices) if prices else 1.0
        price_factor = current_price / max_price if max_price > 0 else 0
        braking_threshold_ratio = 1.0 - (sensor_data['aggressiveness'] / 5.0) * AGGRESSIVENESS_SCALING_FACTOR

        decision_triggers = {
            'braking_by_price': 'price',
            'braking_by_temp': 'temperature',
            'heating': 'temperature',
            'cooling': 'temperature',
            'summer_mode': 'summer',
            'neutral': 'neutral',
            'preboost': 'pre-boost (cold & expensive forecast)',
            'error': 'error in calculation',
        }

        decision_reason = f"{mode} - Triggered by {decision_triggers.get(mode, 'unknown')}"
        next_3_hours_prices = safe_array_slice(prices, now_hour, 3)

        attributes = {
            "Mode": mode,
            "Fake Outdoor Temperature": self._state,
            "Price Category": price_category,
            "Status": "OK",
            "Current Price": round(current_price, 3),
            "Max Price": round(max_price, 3),
            "Aggressiveness": sensor_data['aggressiveness'],
            "Inertia": sensor_data['inertia'],
            "Target Temperature": sensor_data['target_temp'],
            "Indoor Temperature": sensor_data['indoor_temp'],
            "Outdoor Temperature": sensor_data['outdoor_temp'],
            "Summer Threshold": sensor_data['summer_threshold'],
            "Braking Threshold (%)": round(braking_threshold_ratio * 100, 1),
            "Price Factor (%)": round(price_factor * 100, 1),
            "Holiday Mode": holiday,
            "Last Updated": dt_util.now().isoformat(),
            "Temp Error (°C)": round(sensor_data['indoor_temp'] - sensor_data['target_temp'], 2),
            "To Summer Threshold (°C)": round(sensor_data['summer_threshold'] - sensor_data['outdoor_temp'], 2),
            "Next 3 Hours Prices": next_3_hours_prices,
            "Saving Potential (SEK/kWh)": round(max_price - current_price, 3),
            "Decision Reason": decision_reason,
            "Price Categories All Hours": categories,
            "Current Hour": now_hour,
            "Data Quality": {
                "prices_count": len(prices),
                "categories_count": len(categories),
                "forecast_available": bool(sensor_data['outdoor_temp_forecast_entity'])
            }
        }

        return attributes

    async def async_update(self) -> None:
        """Uppdatera sensordata."""
        try:
            update_time = dt_util.now()
            now_hour = update_time.hour

            config = {**self._config_entry.data, **self._config_entry.options}
            sensor_data = self._get_sensor_data(config)
            prices, current_price, price_category, categories = await self._get_price_data(config, now_hour)
            self._last_price_category = price_category

            missing = self._validate_required_data(sensor_data, prices)
            if missing:
                self._state = STATE_UNAVAILABLE
                self._attributes = {
                    "Status": f"Missing: {', '.join(missing)}",
                    "Last Updated": update_time.isoformat(),
                    "Current Hour": now_hour,
                    "ML_Available": self.ml_collector is not None
                }
                return

            holiday = is_holiday_mode_active(
                self.hass,
                HARDCODED_ENTITIES["holiday_mode_boolean_entity"],
                HARDCODED_ENTITIES["holiday_start_datetime_entity"],
                HARDCODED_ENTITIES["holiday_end_datetime_entity"]
            )

            if holiday:
                sensor_data['target_temp'] = HOLIDAY_TEMP

            fake_temp, mode = self._calculate_output_temperature(
                sensor_data, prices, price_category, now_hour
            )
            self._state = round(fake_temp, 1)

            self._attributes = self._build_attributes(
                sensor_data, prices, current_price, price_category,
                mode, holiday, categories, now_hour
            )

            if self.ml_collector:
                self._collect_ml_data(sensor_data, mode, fake_temp)

        except Exception as e:
            if not self.ml_collector:
                self._attributes["ML_Available"] = False
                self._attributes["ML_Error"] = "ML Collector not initialized"
            _LOGGER.error(f"Error during update: {e}", exc_info=True)
            self._state = STATE_UNAVAILABLE
            self._attributes = {
                "Status": f"Error: {str(e)}",
                "Last Updated": dt_util.now().isoformat(),
                "Error Details": str(e),
                "ML_Available": self.ml_collector is not None
            }

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sätt upp sensorn."""
    sensor = PumpSteerSensor(hass, config_entry)
    async_add_entities([sensor], update_before_add=True)
