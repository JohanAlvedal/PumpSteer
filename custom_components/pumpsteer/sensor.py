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

from .pre_boost import check_combined_preboost
from .holiday import is_holiday_mode_active, HOLIDAY_TARGET_TEMPERATURE
from .temp_control_logic import calculate_temperature_output
from .electricity_price import hybrid_classify_prices
from .settings import (
    DEFAULT_HOUSE_INERTIA,
    HOLIDAY_TEMP,
    BRAKING_MODE_TEMP,
    PREBOOST_MAX_OUTDOOR_TEMP,
    AGGRESSIVENESS_SCALING_FACTOR
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
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique identifier."""
        return self._attr_unique_id

    @property
    def state(self) -> StateType:
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        return {
            **self._attributes,
            "friendly_name": "PumpSteer"
        }

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self._attr_unit_of_measurement

    @property
    def device_class(self) -> str:
        """Return the device class."""
        return self._attr_device_class

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:thermostat-box"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._state != STATE_UNAVAILABLE

    @property
    def should_poll(self) -> bool:
        """Return True if the entity should be polled."""
        return True

    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle configuration options updates."""
        self._config_entry = entry
        await self.async_update()

    def _get_sensor_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and validate sensor data from Home Assistant."""
        return {
            'indoor_temp': safe_float(get_state(self.hass, config.get("indoor_temp_entity"))),
            'outdoor_temp': safe_float(get_state(self.hass, config.get("real_outdoor_entity"))),
            'target_temp': safe_float(get_state(self.hass, config.get("target_temp_entity"))),
            'summer_threshold': safe_float(get_state(self.hass, config.get("summer_threshold_entity"))) or DEFAULT_SUMMER_THRESHOLD,
            'aggressiveness': safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or DEFAULT_AGGRESSIVENESS,
            'inertia': safe_float(get_state(self.hass, "input_number.house_inertia")) or DEFAULT_HOUSE_INERTIA
        }

    def _get_price_data(self, config: Dict[str, Any]) -> tuple[list, float, str]:
        """Extract and process electricity price data."""
        prices_raw = get_attr(self.hass, config.get("electricity_price_entity"), "today")
        if not prices_raw:
            prices_raw = get_attr(self.hass, config.get("electricity_price_entity"), "raw_today")

        prices = []
        if isinstance(prices_raw, list):
            for i, p in enumerate(prices_raw):
                try:
                    prices.append(float(p))
                except Exception:
                    _LOGGER.warning(f"PumpSteer: Invalid electricity price at index {i}: {p}")

        now_hour = datetime.now().hour
        current_price = prices[now_hour] if prices and now_hour < len(prices) else 0.0

        if prices and now_hour < len(prices):
            price_category = hybrid_classify_prices(prices)[now_hour] + " (hybrid)"
        else:
            price_category = "unknown" # Changed from "okänd"

        return prices, current_price, price_category

    def _validate_required_data(self, sensor_data: Dict[str, Any], prices: list) -> Optional[list]:
        """Validate that all necessary sensor data is available."""
        missing = []

        if sensor_data['indoor_temp'] is None:
            missing.append("Indoor temperature") # Changed from "Inomhustemperatur"
        if sensor_data['outdoor_temp'] is None:
            missing.append("Outdoor temperature") # Changed from "Utomhustemperatur"
        if sensor_data['target_temp'] is None:
            missing.append("Target temperature") # Changed from "Måltemperatur"
        if not prices:
            missing.append("Electricity prices") # Changed from "Elpriser"

        return missing if missing else None

    def _calculate_output_temperature(self, sensor_data: Dict[str, Any], price_category: str) -> tuple[float, str]:
        """Calculate the output temperature based on current conditions."""
        indoor_temp = sensor_data['indoor_temp']
        outdoor_temp = sensor_data['outdoor_temp']
        target_temp = sensor_data['target_temp']
        summer_threshold = sensor_data['summer_threshold']
        aggressiveness = sensor_data['aggressiveness']

        # Check for summer mode
        if outdoor_temp >= summer_threshold:
            return BRAKING_MODE_TEMP, "summer_mode"

        # Check for expensive electricity periods
        # Assuming PRICE_CATEGORIES in electricity_price.py are also translated,
        # otherwise ensure consistency or map them here.
        # Original: if price_category.startswith("dyrt") or price_category.startswith("extremt_dyrt"):
        if "expensive" in price_category or "extremely_expensive" in price_category: # Adjusted to match expected English categories
            now_hour = datetime.now().hour
            _LOGGER.info(f"PumpSteer: Blocking heating at hour {now_hour} due to {price_category} price (setting fake temp to {BRAKING_MODE_TEMP} °C)") # Changed comment
            return BRAKING_MODE_TEMP, "braking_by_price"

        # Calculate temperature difference
        temp_diff = indoor_temp - target_temp

        # If within neutral zone, use real outdoor temperature
        if abs(temp_diff) <= NEUTRAL_TEMP_THRESHOLD:
            return outdoor_temp, "neutral"

        # Use temperature control logic for heating/cooling
        fake_temp, mode = calculate_temperature_output(
            indoor_temp,
            target_temp,
            outdoor_temp,
            aggressiveness
        )
        return fake_temp, mode

    def _build_attributes(self, sensor_data: Dict[str, Any], prices: list, current_price: float,
                          price_category: str, mode: str, holiday: bool) -> Dict[str, Any]:
        """Build the attribute dictionary for the sensor."""
        now_hour = datetime.now().hour
        max_price = max(prices) if prices else 1.0
        price_factor = current_price / max_price if max_price > 0 else 0

        # Use aggressiveness scaling from settings
        braking_threshold_ratio = 1.0 - (sensor_data['aggressiveness'] / 5.0) * AGGRESSIVENESS_SCALING_FACTOR

        # Build decision reason
        decision_triggers = {
            'braking_by_price': 'price', # Changed from 'pris'
            'heating': 'temperature',    # Changed from 'temperatur'
            'cooling': 'temperature',    # Changed from 'temperatur'
            'summer_mode': 'summer',     # Changed from 'sommar'
            'neutral': 'neutral'
        }
        decision_reason = f"{mode} - Triggered by {decision_triggers.get(mode, 'unknown')}" # Changed from 'okänd'

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
            "Saving Potential (SEK/kWh)": round(max_price - current_price, 3), # Kept SEK/kWh as it's a unit, unless specified otherwise
            "Decision Reason": decision_reason
        }

    async def async_update(self) -> None:
        """Update the sensor's state and attributes."""
        try:
            config = {**self._config_entry.data, **self._config_entry.options}

            # Get sensor data
            sensor_data = self._get_sensor_data(config)

            # Get price data
            prices, current_price, price_category = self._get_price_data(config)

            # Validate required data
            missing = self._validate_required_data(sensor_data, prices)
            if missing:
                self._state = STATE_UNAVAILABLE
                self._attributes = {
                    "Status": f"Missing: {', '.join(missing)}", # Changed from "Saknas"
                    "Last Updated": datetime.now().isoformat()
                }
                _LOGGER.warning(f"PumpSteer: Missing sensor data: {', '.join(missing)}") # Changed from "Saknad sensordata"
                return

            # Check holiday mode
            holiday = is_holiday_mode_active(
                self.hass,
                config.get("holiday_mode_boolean_entity"),
                config.get("holiday_start_datetime_entity"),
                config.get("holiday_end_datetime_entity")
            )

            # Adjust target temperature for holiday mode
            if holiday:
                sensor_data['target_temp'] = HOLIDAY_TEMP

            # Calculate output temperature
            fake_temp, mode = self._calculate_output_temperature(sensor_data, price_category)
            self._state = round(fake_temp, 1)

            # Build attributes
            self._attributes = self._build_attributes(
                sensor_data, prices, current_price, price_category, mode, holiday
            )

            self._last_update_time = datetime.now()
            _LOGGER.debug(f"PumpSteer: Updated - Mode: {mode}, State: {self._state}°C") # Changed from "Uppdaterad - Läge: {mode}, Tillstånd"

        except Exception as e:
            _LOGGER.error(f"PumpSteer: Error during update: {e}") # Changed from "Fel vid uppdatering"
            self._state = STATE_UNAVAILABLE
            self._attributes = {
                "Status": f"Error: {str(e)}", # Changed from "Fel"
                "Last Updated": datetime.now().isoformat()
            }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PumpSteer sensor from a config entry."""
    _LOGGER.debug("PumpSteer: Setting up sensor platform")

    # Create the sensor
    sensor = PumpSteerSensor(hass, config_entry)

    # Add the sensor
    async_add_entities([sensor], update_before_add=True)

    _LOGGER.info("PumpSteer: Sensor platform setup complete")
