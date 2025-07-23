import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .pre_boost import check_combined_preboost  # Keep this import
from .holiday import is_holiday_mode_active, HOLIDAY_TARGET_TEMPERATURE
from .temp_control_logic import calculate_temperature_output
from .electricity_price import async_hybrid_classify_with_history, classify_prices
from .settings import (
    DEFAULT_HOUSE_INERTIA,
    HOLIDAY_TEMP,
    BRAKING_MODE_TEMP,
    PREBOOST_MAX_OUTDOOR_TEMP,  # Add this import
    AGGRESSIVENESS_SCALING_FACTOR,
    PREBOOST_OUTPUT_TEMP  # Add this import
)
from .utils import (
    safe_float, get_state, get_attr,
    safe_get_price_data, safe_parse_temperature_forecast,
    validate_required_entities, safe_get_entity_state_with_description,
    safe_array_slice
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

# Local constants not found in settings.py
NEUTRAL_TEMP_THRESHOLD = 0.5
DEFAULT_SUMMER_THRESHOLD = 18.0
DEFAULT_AGGRESSIVENESS = 0.0


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
            sw_version="1.0.0"
        )

        config_entry.add_update_listener(self.async_options_update_listener)
        _LOGGER.debug("PumpSteerSensor: Initializing")

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

    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._config_entry = entry
        await self.async_update()

    def _get_sensor_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'indoor_temp': safe_float(get_state(self.hass, config.get("indoor_temp_entity"))),
            'outdoor_temp': safe_float(get_state(self.hass, config.get("real_outdoor_entity"))),
            'target_temp': safe_float(get_state(self.hass, config.get("target_temp_entity"))),
            'summer_threshold': safe_float(get_state(self.hass, config.get("summer_threshold_entity"))) or DEFAULT_SUMMER_THRESHOLD,
            'aggressiveness': safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or DEFAULT_AGGRESSIVENESS,
            'inertia': safe_float(get_state(self.hass, "input_number.house_inertia")) or DEFAULT_HOUSE_INERTIA,
            'outdoor_temp_forecast_entity': config.get("outdoor_temp_forecast_entity")
        }

    def _validate_required_data(self, sensor_data: Dict[str, Any], prices: list) -> Optional[list]:
        missing = []

        if sensor_data['indoor_temp'] is None:
            missing.append("Indoor temperature")
        if sensor_data['outdoor_temp'] is None:
            missing.append("Outdoor temperature")
        if sensor_data['target_temp'] is None:
            missing.append("Target temperature")
        if not prices:
            missing.append("Electricity prices")
        if sensor_data['outdoor_temp_forecast_entity'] and not get_state(self.hass, sensor_data['outdoor_temp_forecast_entity']):
            missing.append("Outdoor temperature forecast entity not available")
        elif not sensor_data['outdoor_temp_forecast_entity']:
            _LOGGER.debug("PumpSteer: Outdoor temperature forecast entity not configured, skipping pre-boost temperature forecast check.")

        return missing if missing else None

    def _calculate_output_temperature(self, sensor_data: Dict[str, Any], prices: list, price_category: str) -> tuple[float, str]:
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
                preboost_mode = check_combined_preboost(
                    temp_csv=temp_forecast_csv,
                    prices=prices,
                    cold_threshold=target_temp - 2.0,
                    aggressiveness=aggressiveness,
                    inertia=inertia
                )
            else:
                _LOGGER.debug("PumpSteer: No temperature forecast available for pre-boost check.")

        if preboost_mode == "preboost":
            _LOGGER.info(f"PumpSteer: Pre-boost activated. Setting fake temp to {PREBOOST_OUTPUT_TEMP} °C")
            return PREBOOST_OUTPUT_TEMP, "preboost"

        if outdoor_temp >= summer_threshold:
            return outdoor_temp, "summer_mode"

        if "expensive" in price_category or "very_expensive" in price_category:
            now_hour = datetime.now().hour
            _LOGGER.info(f"PumpSteer: Blocking heating at hour {now_hour} due to {price_category} price (setting fake temp to {BRAKING_MODE_TEMP} °C)")
            return BRAKING_MODE_TEMP, "braking_by_price"

        temp_diff = indoor_temp - target_temp

        if abs(temp_diff) <= NEUTRAL_TEMP_THRESHOLD:
            return outdoor_temp, "neutral"

        fake_temp, mode = calculate_temperature_output(
            indoor_temp,
            target_temp,
            outdoor_temp,
            aggressiveness
        )
        return fake_temp, mode

    def _build_attributes(self, sensor_data: Dict[str, Any], prices: list, current_price: float,
                          price_category: str, mode: str, holiday: bool, categories: list) -> Dict[str, Any]:
        now_hour = datetime.now().hour
        max_price = max(prices) if prices else 1.0
        price_factor = current_price / max_price if max_price > 0 else 0

        braking_threshold_ratio = 1.0 - (sensor_data['aggressiveness'] / 5.0) * AGGRESSIVENESS_SCALING_FACTOR

        decision_triggers = {
            'braking_by_price': 'price',
            'heating': 'temperature',
            'cooling': 'temperature',
            'summer_mode': 'summer',
            'neutral': 'neutral',
            'preboost': 'pre-boost (cold & expensive forecast)'
        }
        decision_reason = f"{mode} - Triggered by {decision_triggers.get(mode, 'unknown')}"

        return {
            "Mode": mode,
            "Fake Outdoor Temperature": self._state,
            "Price Category": price_category,
            "Status": "OK",
            "Current Price": current_price,
            "Max Price": max_price,
            "Aggressiveness": sensor_data['aggressiveness'],
            "Inertia": sensor_data['inertia'],
            "Target Temperature": sensor_data['target_temp'],
            "Indoor Temperature": sensor_data['indoor_temp'],
            "Outdoor Temperature": sensor_data['outdoor_temp'],
            "Summer Threshold": sensor_data['summer_threshold'],
            "Braking Threshold (%)": round(braking_threshold_ratio * 100, 1),
            "Price Factor (%)": round(price_factor * 100, 1),
            "Holiday Mode": holiday,
            "Last Updated": datetime.now().isoformat(),
            "Temp Error (°C)": round(sensor_data['indoor_temp'] - sensor_data['target_temp'], 2),
            "To Summer Threshold (°C)": round(sensor_data['summer_threshold'] - sensor_data['outdoor_temp'], 2),
            "Next 3 Hours Prices": prices[now_hour:now_hour+3] if len(prices) >= now_hour + 3 else prices[now_hour:],
            "Saving Potential (SEK/kWh)": round(max_price - current_price, 3),
            "Decision Reason": decision_reason,
            "Price Categories All Hours": categories,
        }

    # async def _get_price_data(self, config: Dict[str, Any]) -> tuple[list, float, str, list]:
    #     """Get and classify prices using Tibber-model with trailing average."""
    #     entity_id = config.get("electricity_price_entity")

    #     prices_raw = get_attr(self.hass, entity_id, "today") or get_attr(self.hass, entity_id, "raw_today")

    #     if not prices_raw:
    #         _LOGGER.warning(f"PumpSteer: Could not retrieve electricity prices from {entity_id}")
    #         return [], 0.0, "unknown", []

    #     prices = [float(p) for p in prices_raw if isinstance(p, (float, int))]

    #     now_hour = datetime.now().hour
    #     current_price = prices[now_hour] if prices and now_hour < len(prices) else 0.0

    #     categories = await async_hybrid_classify_with_history(
    #         self.hass,
    #         price_list=prices,
    #         price_entity_id=entity_id,
    #         trailing_hours=72
    #     )

    #     price_category = categories[now_hour] + " (hybrid)" if categories and now_hour < len(categories) else "unknown"
    #     return prices, current_price, price_category, categories
    async def _get_price_data(self, config: Dict[str, Any]) -> tuple[list, float, str, list]:
        entity_id = config.get("electricity_price_entity")
    
        prices_raw = get_attr(self.hass, entity_id, "today") or get_attr(self.hass, entity_id, "raw_today")
        if not prices_raw:
            _LOGGER.warning(f"PumpSteer: Could not retrieve electricity prices from {entity_id}")
            return [], 0.0, "unknown", []
    
        prices = [float(p) for p in prices_raw if isinstance(p, (float, int))]
        now_hour = datetime.now().hour
        current_price = prices[now_hour] if prices and now_hour < len(prices) else 0.0
    
        # 🔀 Läs från input_select
        mode = get_state(self.hass, "input_select.pumpsteer_price_model") or "hybrid"
        categories = []
    
        if mode == "percentiles":
            categories = classify_prices(prices)
            price_category = categories[now_hour] + " (percentiles)" if now_hour < len(categories) else "unknown"
        else:
            categories = await async_hybrid_classify_with_history(
                self.hass,
                price_list=prices,
                price_entity_id=entity_id,
                trailing_hours=72
            )
            price_category = categories[now_hour] + " (hybrid)" if now_hour < len(categories) else "unknown"
    
        return prices, current_price, price_category, categories

    async def async_update(self) -> None:
        try:
            config = {**self._config_entry.data, **self._config_entry.options}

            sensor_data = self._get_sensor_data(config)
            prices, current_price, price_category, categories = await self._get_price_data(config)

            missing = self._validate_required_data(sensor_data, prices)
            if missing:
                self._state = STATE_UNAVAILABLE
                self._attributes = {
                    "Status": f"Missing: {', '.join(missing)}",
                    "Last Updated": datetime.now().isoformat()
                }
                _LOGGER.warning(f"PumpSteer: Missing sensor data: {', '.join(missing)}")
                return

            holiday = is_holiday_mode_active(
                self.hass,
                config.get("holiday_mode_boolean_entity"),
                config.get("holiday_start_datetime_entity"),
                config.get("holiday_end_datetime_entity")
            )

            if holiday:
                sensor_data['target_temp'] = HOLIDAY_TEMP

            fake_temp, mode = self._calculate_output_temperature(sensor_data, prices, price_category)
            self._state = round(fake_temp, 1)

            self._attributes = self._build_attributes(
                sensor_data, prices, current_price, price_category, mode, holiday, categories
            )

            self._last_update_time = datetime.now()
            _LOGGER.debug(f"PumpSteer: Updated - Mode: {mode}, State: {self._state}°C")

        except Exception as e:
            _LOGGER.error(f"PumpSteer: Error during update: {e}", exc_info=True)
            self._state = STATE_UNAVAILABLE
            self._attributes = {
                "Status": f"Error: {str(e)}",
                "Last Updated": datetime.now().isoformat()
            }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    _LOGGER.debug("PumpSteer: Setting up sensor platform")

    sensor = PumpSteerSensor(hass, config_entry)

    async_add_entities([sensor], update_before_add=True)

    _LOGGER.info("PumpSteer: Sensor platform setup complete")
