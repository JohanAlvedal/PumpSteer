# sensor.py

import logging
from typing import Optional, Dict, Any, Tuple, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

# Import existing modules
from ..pre_boost import check_combined_preboost
from ..holiday import is_holiday_mode_active
from ..temp_control_logic import calculate_temperature_output
from ..electricity_price import async_hybrid_classify_with_history, classify_prices
from ..settings import (
    DEFAULT_HOUSE_INERTIA,
    HOLIDAY_TEMP,
    BRAKING_MODE_TEMP,
    BRAKE_FAKE_TEMP,
    PREBOOST_MAX_OUTDOOR_TEMP,
    AGGRESSIVENESS_SCALING_FACTOR,
    PREBOOST_OUTPUT_TEMP,
    WINTER_BRAKE_TEMP_OFFSET,
    CHEAP_PRICE_OVERSHOOT,
)
from ..utils import (
    safe_float,
    get_state,
    get_attr,
    safe_array_slice,
    get_version,
    should_precool,
)

_LOGGER = logging.getLogger(__name__)

# Simple ML import
try:
    from ..ml_adaptive import PumpSteerMLCollector
    ML_AVAILABLE = True
    _LOGGER.info("ML features available")
except ImportError as e:
    ML_AVAILABLE = False
    _LOGGER.warning(f"ML features disabled: {e}")


DOMAIN = "pumpsteer"


SW_VERSION = get_version()

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
    "price_model_entity": "input_select.pumpsteer_price_model",
    "preboost_enabled_entity": "input_boolean.pumpsteer_preboost_enabled",
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
    """Safely get current price and category for a given hour."""
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
    """PumpSteer sensor for heat pump control."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the PumpSteer sensor."""
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
            sw_version=SW_VERSION,
        )

        # Simple ML initialization
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
        """Called when the entity is added to Home Assistant."""
        if self.ml_collector and hasattr(self.ml_collector, 'async_load_data'):
            try:
                await self.ml_collector.async_load_data()
                _LOGGER.debug("ML data loaded successfully")
            except Exception as e:
                _LOGGER.error(f"Failed to load ML data: {e}")
                self.ml_collector = None

        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal from Home Assistant."""
        if self.ml_collector and hasattr(self.ml_collector, "async_shutdown"):
            try:
                await self.ml_collector.async_shutdown()
            except Exception as e:
                _LOGGER.error(f"Error during ML collector shutdown: {e}")
        self.ml_collector = None
        await super().async_will_remove_from_hass()


    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle options update event."""
        self._config_entry = entry
        await self.async_update()


    def _get_sensor_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch sensor data from Home Assistant."""
        return {
            'indoor_temp': safe_float(get_state(self.hass, config.get("indoor_temp_entity"))),
            'outdoor_temp': safe_float(get_state(self.hass, config.get("real_outdoor_entity"))),
            'target_temp': safe_float(get_state(self.hass, HARDCODED_ENTITIES["target_temp_entity"])),
            'summer_threshold': safe_float(get_state(self.hass, HARDCODED_ENTITIES["summer_threshold_entity"])) or DEFAULT_SUMMER_THRESHOLD,
            'aggressiveness': safe_float(get_state(self.hass, HARDCODED_ENTITIES["aggressiveness_entity"])) or DEFAULT_AGGRESSIVENESS,
            'inertia': safe_float(get_state(self.hass, HARDCODED_ENTITIES["house_inertia_entity"])) or DEFAULT_HOUSE_INERTIA,
            'outdoor_temp_forecast_entity': HARDCODED_ENTITIES["hourly_forecast_temperatures_entity"],
            'preboost_enabled': (get_state(self.hass, HARDCODED_ENTITIES["preboost_enabled_entity"]) == "on")
        }


    def _validate_required_data(self, sensor_data: Dict[str, Any], prices: List[float]) -> Optional[List[str]]:
        missing = []

        if sensor_data['indoor_temp'] is None:
            missing.append("Indoor temperature")
        if sensor_data['outdoor_temp'] is None:
            missing.append("Outdoor temperature")
        if sensor_data['target_temp'] is None:
            missing.append("Target temperature")
        if not prices:
            missing.append("Electricity prices")

        # Only require forecast data if preboost is enabled
        if sensor_data.get('preboost_enabled') and sensor_data['outdoor_temp_forecast_entity'] \
        and get_state(self.hass, sensor_data['outdoor_temp_forecast_entity']) is None:
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
        """Calculate output temperature based on current conditions."""
        indoor_temp = sensor_data['indoor_temp']
        outdoor_temp = sensor_data['outdoor_temp']
        target_temp = sensor_data['target_temp']
        summer_threshold = sensor_data['summer_threshold']
        aggressiveness = sensor_data['aggressiveness']
        inertia = sensor_data['inertia']
        outdoor_temp_forecast_entity = sensor_data['outdoor_temp_forecast_entity']

        preboost_mode = None
        temp_forecast_csv = None

        # Fetch forecast if entity provided
        if outdoor_temp_forecast_entity:
            temp_forecast_csv = get_state(self.hass, outdoor_temp_forecast_entity)

        # Allow preboost only if switch is ON and outdoor temperature is low
        preboost_allowed = bool(sensor_data.get('preboost_enabled', False))

        if (
            preboost_allowed
            and outdoor_temp < PREBOOST_MAX_OUTDOOR_TEMP
            and temp_forecast_csv
        ):
            try:
                preboost_mode = check_combined_preboost(
                    temp_csv=temp_forecast_csv,
                    prices=prices,
                    cold_threshold=target_temp - 2.0,
                    # Provide aggressiveness in the 0-5 range for pre-boost logic
                    aggressiveness=aggressiveness,
                    inertia=inertia,
                )
            except Exception as e:
                _LOGGER.error(f"Error in pre-boost check: {e}")
                preboost_mode = None
        elif preboost_allowed and outdoor_temp < PREBOOST_MAX_OUTDOOR_TEMP:
            _LOGGER.debug("No temperature forecast available for pre-boost check.")
        elif not preboost_allowed:
            _LOGGER.debug("Pre-boost disabled by switch; skipping pre-boost evaluation.")

        if preboost_mode == "preboost":
            _LOGGER.info(f"Pre-boost activated. Setting fake temp to {PREBOOST_OUTPUT_TEMP} °C")
            return PREBOOST_OUTPUT_TEMP, "preboost"

        if temp_forecast_csv and should_precool(temp_forecast_csv, summer_threshold):
            _LOGGER.info(
                "Activating summer precool mode due to forecasted high temperatures"
            )
            return BRAKE_FAKE_TEMP, "precool"

        if outdoor_temp >= summer_threshold:
            return outdoor_temp, "summer_mode"

        # Allow slight overshoot only when prices are very cheap
        target_temp_for_logic = target_temp
        if "very_cheap" in price_category:
            target_temp_for_logic += CHEAP_PRICE_OVERSHOOT

        # Dynamic braking temperature based on outdoor temp
        brake_temp = (
            outdoor_temp + WINTER_BRAKE_TEMP_OFFSET
            if outdoor_temp < summer_threshold
            else BRAKE_FAKE_TEMP
        )

        temp_diff = indoor_temp - target_temp_for_logic

        if abs(temp_diff) <= NEUTRAL_TEMP_THRESHOLD:
            fake_temp = outdoor_temp
            mode = "neutral"
        else:
            try:
                fake_temp, mode = calculate_temperature_output(
                    indoor_temp,
                    target_temp_for_logic,
                    outdoor_temp,
                    aggressiveness,
                    brake_temp,
                )
            except Exception as e:
                _LOGGER.error(f"Error in temperature calculation: {e}")
                fake_temp, mode = outdoor_temp, "error"

        if mode not in ["braking_by_temp", "heating"] and (
            "expensive" in price_category
            or "very_expensive" in price_category
            or "extreme" in price_category
        ):
            price_brake_temp = (
                outdoor_temp + WINTER_BRAKE_TEMP_OFFSET
                if outdoor_temp < summer_threshold
                else BRAKING_MODE_TEMP
            )
            _LOGGER.info(
                f"Blocking heating at hour {now_hour} due to {price_category} price (setting fake temp to {price_brake_temp} °C)"
            )
            return price_brake_temp, "braking_by_price"

        fake_temp = min(fake_temp, BRAKE_FAKE_TEMP)
        return fake_temp, mode


    def _collect_ml_data(self, sensor_data: Dict[str, Any], mode: str, fake_temp: float) -> None:
        """Collect data for machine learning."""
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


    def _add_ml_attributes(self) -> None:
        """Add ML attributes to sensor attributes."""
        if not self.ml_collector:
            return

        try:
            ml_status = self.ml_collector.get_status()
            self._attributes.update({
                "ML_Available": True,
                "ML_Status": "Collecting data" if ml_status["collecting_data"] else "Ready",
                "ML_Sessions_Collected": ml_status["sessions_collected"]
            })

        except Exception as e:
            _LOGGER.debug(f"ML attributes error (non-critical): {e}")


    async def _get_price_data(
        self,
        config: Dict[str, Any],
        now_hour: int
    ) -> Tuple[List[float], float, str, List[str]]:
        """Fetch price data and classify prices."""
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
        """Build attribute dictionary for the sensor."""
        max_price = max(prices) if prices else 1.0
        min_price = min(prices) if prices else 0.0

        price_range = max_price - min_price
        if price_range > 0:
            price_factor = (current_price - min_price) / price_range
        else:
            price_factor = 0.0

        price_factor = max(0.0, min(price_factor, 1.0))
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
            "mode": mode,
            "fake_outdoor_temperature": self._state,
            "price_category": price_category,
            "status": "ok",
            "current_price": round(current_price, 3),
            "max_price": round(max_price, 3),
            "aggressiveness": sensor_data['aggressiveness'],
            "inertia": sensor_data['inertia'],
            "target_temperature": sensor_data['target_temp'],
            "indoor_temperature": sensor_data['indoor_temp'],
            "outdoor_temperature": sensor_data['outdoor_temp'],
            "summer_threshold": sensor_data['summer_threshold'],
            "braking_threshold_percent": round(braking_threshold_ratio * 100, 1),
            "price_factor_percent": round(price_factor * 100, 1),
            "holiday_mode": holiday,
            "last_updated": dt_util.now().isoformat(),
            "temp_error_c": round(sensor_data['indoor_temp'] - sensor_data['target_temp'], 2),
            "to_summer_threshold_c": round(sensor_data['summer_threshold'] - sensor_data['outdoor_temp'], 2),
            "next_3_hours_prices": next_3_hours_prices,
            "saving_potential_sek_per_kwh": round(max_price - current_price, 3),
            "decision_reason": decision_reason,
            "price_categories_all_hours": categories,
            "current_hour": now_hour,
            "data_quality": {
                "prices_count": len(prices),
                "categories_count": len(categories),
                "forecast_available": bool(sensor_data['outdoor_temp_forecast_entity'])
            },
            "preboost_enabled": bool(sensor_data.get('preboost_enabled', False)),
        }

        return attributes


    async def async_update(self) -> None:
        """Update sensor data."""
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
                self._add_ml_attributes()

            self._last_update_time = update_time

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
    """Set up the PumpSteer sensor entity."""
    sensor = PumpSteerSensor(hass, config_entry)
    async_add_entities([sensor], update_before_add=True)
