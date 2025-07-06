# Standard imports
import logging
from datetime import datetime, timedelta

# Home Assistant-specific imports
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.typing import StateType  # For state type hinting
from . import settings # import settings.py

# Import async_call_later to schedule updates
from homeassistant.helpers.event import async_call_later

# Custom imports for PumpSteer
from .pre_boost import check_combined_preboost
from .holiday import is_holiday_mode_active, HOLIDAY_TARGET_TEMPERATURE # Added holiday imports

_LOGGER = logging.getLogger(__name__)

# Constants for inertia calculation
INERTIA_UPDATE_INTERVAL = timedelta(minutes=10)  # How often to check delta
INERTIA_WEIGHT_FACTOR = 4  # How much old inertia should weigh
INERTIA_DIVISOR = 5  # (INERTIA_WEIGHT_FACTOR + 1)
MAX_INERTIA_VALUE = 5.0
MIN_INERTIA_VALUE = 0.0
DEFAULT_INERTIA_VALUE = settings.DEFAULT_HOUSE_INERTIA
PREBOOST_MAX_OUTDOOR_TEMP = settings.PREBOOST_MAX_OUTDOOR_TEMP 

def safe_float(val: StateType) -> float | None:
    """Safely converts a value to float, returns None on error."""
    try:
        if val is None:  # Explicitly handle None
            return None
        return float(val)
    except (TypeError, ValueError):
        return None

def get_state(hass: HomeAssistant, entity_id: str) -> str | None:
    """Safely retrieves the state of an entity. Returns None if entity_id is invalid or state is unavailable/unknown."""
    if not entity_id:
        return None
    entity = hass.states.get(entity_id)
    if entity and entity.state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
        return entity.state
    return None

def get_attr(hass: HomeAssistant, entity_id: str, attribute: str) -> any:
    """Safely retrieves an attribute from an entity. Returns None if entity_id is invalid or attribute is missing."""
    if not entity_id:
        return None
    entity = hass.states.get(entity_id)
    return entity.attributes.get(attribute) if entity and attribute in entity.attributes else None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Sets up the PumpSteer sensor platform."""
    sensors = [
        PumpSteerSensor(hass, entry),
        PumpSteerFutureStrategySensor(hass, entry),
    ]
    async_add_entities(sensors, True)

class PumpSteerSensor(Entity):
    """Representation of a PumpSteer Sensor."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry
        self._state = None
        self._attributes = {}
        self._last_update_time = None
        self._previous_indoor_temp = None
        self._last_outdoor_temp = None
        self._inertia_value = settings.DEFAULT_HOUSE_INERTIA
        self._name = "PumpSteer"

        # Set standard Home Assistant properties
        self._attr_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"
        self._attr_state_class = "measurement"
        self._attr_unique_id = config_entry.entry_id

        # Initialize extra attributes
        self._attributes = {
            "Status": "Initializing",
            "Mode": "initializing",
            "Outdoor (actual)": None,
            "Indoor (target)": None,  # Will be updated with actual_target_temp_for_logic
            "Indoor (actual)": None,
            "Inertia": self._inertia_value,
            "Aggressiveness": None,
            "Summer Threshold": None,
            "Electricity Prices (forecast)": None,
            "Pre-boost Active": False,
        }

        # Add a listener for configuration changes
        config_entry.add_update_listener(self.async_options_update_listener)

        _LOGGER.debug(f"PumpSteerSensor: Initializing with config data: {self._config_entry.data}")
        _LOGGER.debug(f"PumpSteerSensor: Initializing with config options: {self._config_entry.options}")

    @property
    def name(self) -> str:
        """Returns the sensor's name."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Returns a unique ID for the sensor."""
        return f"pumpsteer_{self._config_entry.entry_id}"

    @property
    def state(self) -> StateType:
        """Returns the sensor's state."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Returns the sensor's state attributes."""
        # Combine existing attributes with new, friendly names
        return {
            **self._attributes,
            "friendly_name": "PumpSteer – Control Output"
        }

    @property
    def unit_of_measurement(self) -> str:
        """Returns the unit of measurement."""
        return "°C"

    @property
    def device_class(self) -> str:
        """Returns the device class."""
        return "temperature"

    @property
    def icon(self) -> str:
        """Returns the icon to use in the frontend."""
        return "mdi:thermometer-lines"

    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handles option updates."""
        _LOGGER.debug("PumpSteer: Options updated, reloading sensor.")
        self._config_entry = entry  # Update config_entry to get the latest options
        await self.async_update()  # Call update directly to apply new settings

    async def async_update(self) -> None:
        """Updates the sensor's state."""
        # Combine data and options to get the full configuration
        config = {**self._config_entry.data, **self._config_entry.options}
        
        # Get all entity IDs from the combined configuration
        indoor_temp_entity_id = config.get("indoor_temp_entity")
        real_outdoor_temp_entity_id = config.get("real_outdoor_entity")
        electricity_price_entity_id = config.get("electricity_price_entity")
        hourly_forecast_temperatures_entity_id = config.get("hourly_forecast_temperatures_entity")
        target_temp_entity_id = config.get("target_temp_entity")
        summer_threshold_entity_id = config.get("summer_threshold_entity")
        
        # Get IDs for holiday mode helpers (they may be None if optional and not configured)
        holiday_mode_boolean_entity_id = self._config_entry.options.get("holiday_mode_boolean_entity") or config.get("holiday_mode_boolean_entity")
        holiday_start_datetime_entity_id = self._config_entry.options.get("holiday_start_datetime_entity") or config.get("holiday_start_datetime_entity")
        holiday_end_datetime_entity_id = self._config_entry.options.get("holiday_end_datetime_entity") or config.get("holiday_end_datetime_entity")

        # Get states for entities
        indoor_temp = safe_float(get_state(self.hass, indoor_temp_entity_id))
        real_outdoor_temp = safe_float(get_state(self.hass, real_outdoor_temp_entity_id))
        electricity_prices = get_attr(self.hass, electricity_price_entity_id, "today")  
        hourly_temps_csv = get_state(self.hass, hourly_forecast_temperatures_entity_id)
        
        # Get target temperature and summer threshold from input_number helpers
        configured_target_temp = safe_float(get_state(self.hass, target_temp_entity_id))
        summer_threshold_temp = safe_float(get_state(self.hass, summer_threshold_entity_id))
        
        # Aggressiveness and inertia from helpers (assumed to always exist)
        aggressiveness = safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or 0.0
        user_defined_inertia = safe_float(get_state(self.hass, "input_number.house_inertia"))  
        inertia = user_defined_inertia if user_defined_inertia is not None else settings.DEFAULT_HOUSE_INERTIA
        
        # Collect critical data to check if anything is missing
        critical_entities_data = {
            "Indoor (actual)": indoor_temp,
            "Outdoor (actual)": real_outdoor_temp,
            "Target Temp": configured_target_temp,  # Uses the configured value here
            "Summer Threshold": summer_threshold_temp,
            "Electricity Prices (forecast)": electricity_prices,
            "Temperature Forecast": hourly_temps_csv,
        }

        missing_data_info = [name for name, value in critical_entities_data.items() if value is None]

        if missing_data_info:
            _LOGGER.warning("PumpSteer: Waiting for data for: %s. Retrying in 10 seconds.", ", ".join(missing_data_info))
            self._state = STATE_UNAVAILABLE
            self._attributes["Status"] = f"Waiting for data: {', '.join(missing_data_info)}"
            # Schedule a new update after 10 seconds
            self.async_on_remove(
                async_call_later(self.hass, timedelta(seconds=10), self.async_schedule_update_ha_state)
            )
            return

        self._attributes["Status"] = "OK"
        
        # --- HOLIDAY MODE LOGIC ---
        # Check if holiday mode is active
        holiday_mode_active = False
        if holiday_mode_boolean_entity_id and holiday_start_datetime_entity_id and holiday_end_datetime_entity_id:
            holiday_mode_active = is_holiday_mode_active(
                self.hass,
                holiday_mode_boolean_entity_id,
                holiday_start_datetime_entity_id,
                holiday_end_datetime_entity_id
            )
        
        self._attributes["Holiday Status"] = "Active" if holiday_mode_active else "Inactive"
        # NOTE:
        # Holiday mode is only active when Summer mode is NOT active.
        # If the outdoor temperature is above the summer threshold, Summer mode will always take priority over Holiday mode.
        # This is to ensure that heating is minimized during warm periods, regardless of holiday settings.

        # Determine the actual target temperature to use in calculations
        # Default is the configured temperature
        actual_target_temp_for_logic = configured_target_temp

        if holiday_mode_active:
            actual_target_temp_for_logic = settings.HOLIDAY_TEMP
            self._attributes["Mode"] = "Holiday"
            self._attributes["Holiday Active"] = holiday_mode_active
            _LOGGER.info(f"[PumpSteer] Overriding target temperature to {settings.HOLIDAY_TEMP}°C due to Holiday Mode.")
        elif self._attributes.get("Mode") == "Holiday":  # If we just left holiday mode
            self._attributes["Mode"] = "Normal"  # Reset to Normal (or whatever the default is)

        # --- END HOLIDAY MODE LOGIC ---

        # --- CHECK MODE AND SET OUTPUT VALUE ---
        
        # 1. Summer Mode - highest priority (still uses actual_target_temp_for_logic for logic)
        if real_outdoor_temp >= summer_threshold_temp:
            self._state = round(25.0, 1)  # High value to turn off/minimize heating
            self._attributes["Mode"] = "summer_mode" + (" + holiday" if holiday_mode_active else "")
            self._attributes["Pre-boost Active"] = False
            _LOGGER.info("PumpSteer: Summer Mode activated (Outdoor temp: %.1f >= %.1f)", real_outdoor_temp, summer_threshold_temp)
        elif holiday_mode_active:  # Holiday mode has already been handled above and set Mode to "Holiday"
            # No further logic here, state is set at the end based on actual_target_temp_for_logic
            pass
        else:  # Only if neither summer mode nor holiday mode is active
            # 2. Braking Mode (based on price) - prioritized over pre-boost
            max_price_in_forecast = max(electricity_prices) if electricity_prices else 0.0
            current_price = electricity_prices[0] if electricity_prices and electricity_prices[0] is not None else 0.0

            price_factor = 0.0
            if max_price_in_forecast > 0:
                price_factor = current_price / max_price_in_forecast
            
            # Dynamic threshold based on aggressiveness
            braking_threshold_ratio = 1.0 - (aggressiveness / 5.0) * 0.4  
            
            if price_factor >= braking_threshold_ratio:
                self._state = round(25.0, 1)  # Sets the virtual outdoor temperature to a high level
                self._attributes["Mode"] = "braking_mode"
                self._attributes["Pre-boost Active"] = True  # Use this to pause inertia calculation
                _LOGGER.info("PumpSteer: Braking mode activated due to high price (Aggressiveness: %.1f, Price Factor: %.2f)", aggressiveness, price_factor)
            else:
                # 3. Pre-boost Mode (based on forecast)
                boost_mode = None
                if real_outdoor_temp <= settings.PREBOOST_MAX_OUTDOOR_TEMP:
                    # Use actual_target_temp_for_logic for cold_threshold if needed in check_combined_preboost
                    boost_mode = check_combined_preboost(
                        hourly_temps_csv,
                        electricity_prices,
                        lookahead_hours=settings.MAX_PREBOOST_HOURS,
                        cold_threshold=actual_target_temp_for_logic - settings.PREBOOST_TEMP_THRESHOLD,  # Example: 2 degrees below target temperature
                        price_threshold_ratio=settings.PREBOOST_PRICE_THRESHOLD,
                        aggressiveness=aggressiveness,  
                        inertia=inertia
                    )
                else:
                    _LOGGER.info(f"PumpSteer: Pre-boost deactivated as outdoor temperature ({real_outdoor_temp}°C) is above max threshold ({settings.PREBOOST_MAX_OUTDOOR_TEMP}°C).")
                
                if boost_mode == "preboost":
                    self._state = -15.0  # Very low virtual outdoor temp to accelerate
                    self._attributes["Mode"] = "preboost"
                    self._attributes["Pre-boost Active"] = True
                    _LOGGER.info("PumpSteer: Preboost (accelerate) activated to build heat buffer.")
                else:
                    # 4. Normal operation (heating/neutral)
                    # This logic MUST use actual_target_temp_for_logic
                    diff = indoor_temp - actual_target_temp_for_logic
                    
                    scaling_factor = aggressiveness * 0.5  
                    fake_temp = real_outdoor_temp + (diff * scaling_factor)

                    if diff < 0:
                        # House is colder than target
                        fake_temp = min(fake_temp, 20.0)
                        self._attributes["Mode"] = "heating"
                    else:
                        # House is at or above target
                        fake_temp = max(fake_temp, -10.0)  
                        self._attributes["Mode"] = "neutral" if abs(diff) < 0.5 else "braking_by_temp"
                        
                    self._state = round(fake_temp, 1)
                    self._attributes["Pre-boost Active"] = False
                    _LOGGER.debug("PumpSteer: Normal operation (fake temp: %.1f °C, diff: %.2f) - Mode: %s", fake_temp, diff, self._attributes["Mode"])

        # --- INERTIA CALCULATION ---
        current_time = datetime.now()
        
        # Inertia calculation is paused if Pre-boost or Braking is active.
        # We use the attribute "Pre-boost Active" as a general flag for this.
        if self._last_update_time and (current_time - self._last_update_time) >= INERTIA_UPDATE_INTERVAL:
            if not self._attributes.get("Pre-boost Active") and not self._attributes.get("Mode") == "braking_mode" and not self._attributes.get("Mode") == "summer_mode" and not self._attributes.get("Mode") == "Holiday":
                # Only perform inertia calculation in "Normal" or "heating/neutral" mode
                if self._previous_indoor_temp is not None and self._last_outdoor_temp is not None:
                    delta_indoor = indoor_temp - self._previous_indoor_temp
                    delta_outdoor = real_outdoor_temp - self._last_outdoor_temp
                    if abs(delta_outdoor) > 0.001:
                        new_inertia_contribution = delta_indoor / delta_outdoor
                        new_inertia_contribution = max(-5.0, min(5.0, new_inertia_contribution))
                        
                        self._inertia_value = (self._inertia_value * INERTIA_WEIGHT_FACTOR + new_inertia_contribution) / INERTIA_DIVISOR
                        self._inertia_value = max(MIN_INERTIA_VALUE, min(MAX_INERTIA_VALUE, self._inertia_value))
                        
                        house_inertia_entity_id = "input_number.house_inertia"
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "input_number", "set_value",
                                {"entity_id": house_inertia_entity_id, "value": round(self._inertia_value, 2)},
                                blocking=False,
                            )
                        )
                        _LOGGER.debug(f"PumpSteer: Updated input_number.house_inertia to {self._inertia_value:.2f}")
                    else:
                        _LOGGER.debug("PumpSteer: Delta outdoor too small (%.2f), skipping inertia calculation for this interval.", delta_outdoor)
                else:
                    _LOGGER.debug("PumpSteer: Previous indoor/outdoor temp not available, skipping inertia calculation.")
                self._previous_indoor_temp = indoor_temp
                self._last_outdoor_temp = real_outdoor_temp
                self._last_update_time = current_time
            else:
                _LOGGER.debug("Inertia calculation paused due to current mode (%s). No update.", self._attributes.get("Mode"))
        elif not self._last_update_time:
            self._last_update_time = current_time
            self._previous_indoor_temp = indoor_temp
            self._last_outdoor_temp = real_outdoor_temp

        current_inertia = user_defined_inertia if user_defined_inertia is not None else settings.DEFAULT_HOUSE_INERTIA

        # Update attributes
        self._attributes.update({
            "Outdoor (actual)": real_outdoor_temp,
            "Indoor (target)": actual_target_temp_for_logic,  # Shows the actual target temp used
            "Indoor (actual)": indoor_temp,
            "Inertia": round(current_inertia, 2),
            "Aggressiveness": aggressiveness,
            "Summer Threshold": summer_threshold_temp,
            "Electricity Prices (forecast)": electricity_prices,
            "Pre-boost Active": self._attributes.get("Pre-boost Active", False),
            # "Mode" is already set in the if/elif statements above
        })
        _LOGGER.debug(f"PumpSteer: Final state: {self._state}°C, Mode: {self._attributes['Mode']}")


class PumpSteerFutureStrategySensor(Entity):
    """Representation of a PumpSteer Future Strategy Sensor."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry
        self._state = "Unknown"  # State will be the future strategy
        self._attributes = {}
        self._name = "PumpSteer Future Strategy"

        self._attr_unique_id = f"pumpsteer_future_strategy_{config_entry.entry_id}"

        self._attributes = {
            "Status": "Initializing",
            "Pre-boost Expected": False,
            "Cold Threshold Used": None,
            "Price Threshold Ratio Used": None,
            "Lookahead Hours": None,
            "Forecast Temperature (next 6h)": None,
            "Forecast Prices (next 6h)": None,
        }

        config_entry.add_update_listener(self.async_options_update_listener)

        _LOGGER.debug(f"PumpSteerFutureStrategySensor: Initializing with config data: {self._config_entry.data}")
        _LOGGER.debug(f"PumpSteerFutureStrategySensor: Initializing with config options: {self._config_entry.options}")

    @property
    def name(self) -> str:
        """Returns the sensor's name."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Returns a unique ID for the sensor."""
        return self._attr_unique_id

    @property
    def state(self) -> StateType:
        """Returns the sensor's state."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Returns the sensor's state attributes."""
        return {
            **self._attributes,
            "friendly_name": "PumpSteer – Future Strategy"
        }

    @property
    def icon(self) -> str:
        """Returns the icon to use in the frontend."""
        return "mdi:chart-timeline-variant" # An icon representing future/forecast

    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handles option updates."""
        _LOGGER.debug("PumpSteerFutureStrategySensor: Options updated, reloading sensor.")
        self._config_entry = entry
        await self.async_update()

    async def async_update(self) -> None:
        """Updates the sensor's state based on future predictions."""
        config = {**self._config_entry.data, **self._config_entry.options}

        real_outdoor_temp_entity_id = config.get("real_outdoor_entity")
        electricity_price_entity_id = config.get("electricity_price_entity")
        hourly_forecast_temperatures_entity_id = config.get("hourly_forecast_temperatures_entity")
        target_temp_entity_id = config.get("target_temp_entity") # Added for future strategy logic

        real_outdoor_temp = safe_float(get_state(self.hass, real_outdoor_temp_entity_id))
        electricity_prices = get_attr(self.hass, electricity_price_entity_id, "today")
        hourly_temps_csv = get_state(self.hass, hourly_forecast_temperatures_entity_id)
        
        # Get target temperature and summer threshold from input_number helpers
        configured_target_temp = safe_float(get_state(self.hass, target_temp_entity_id))
        
        aggressiveness = safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or 0.0
        user_defined_inertia = safe_float(get_state(self.hass, "input_number.house_inertia"))
        inertia = user_defined_inertia if user_defined_inertia is not None else DEFAULT_INERTIA_VALUE # Use DEFAULT_INERTIA_VALUE if user_defined_inertia is None for future calculations.

        # Collect critical data, similar to PumpSteerSensor
        critical_data = {
            "Outdoor (actual)": real_outdoor_temp,
            "Target Temp": configured_target_temp,
            "Electricity Prices (forecast)": electricity_prices,
            "Temperature Forecast": hourly_temps_csv,
        }

        missing_data = [name for name, value in critical_data.items() if value is None]

        if missing_data:
            _LOGGER.warning("PumpSteerFutureStrategySensor: Waiting for data for: %s. Retrying in 10 seconds.", ", ".join(missing_data))
            self._state = STATE_UNAVAILABLE
            self._attributes["Status"] = f"Waiting for data: {', '.join(missing_data)}"
            self.async_on_remove(
                async_call_later(self.hass, timedelta(seconds=10), self.async_schedule_update_ha_state)
            )
            return

        self._attributes["Status"] = "OK"

        # Define parameters for future pre-boost check
        # These should ideally be configurable, but for now use static values or derive from aggressiveness
        lookahead_hours = settings.MAX_PREBOOST_HOURS
        cold_threshold_for_future = configured_target_temp - settings.PREBOOST_TEMP_THRESHOLD
        price_threshold_ratio_for_future = settings.PREBOOST_PRICE_THRESHOLD
        
        boost_mode = None
        if real_outdoor_temp <= settings.PREBOOST_MAX_OUTDOOR_TEMP:
            # Check for pre-boost in the future
            boost_mode = check_combined_preboost(
                hourly_temps_csv,
                electricity_prices,
                lookahead_hours=lookahead_hours,
                cold_threshold=cold_threshold_for_future,
                price_threshold_ratio=price_threshold_ratio_for_future,
                aggressiveness=aggressiveness,
                inertia=inertia
            )
            _LOGGER.debug(f"Future strategy check: boost_mode = {boost_mode}")
        else:
            _LOGGER.debug(f"Future strategy: Pre-boost not considered as outdoor temp ({real_outdoor_temp}°C) is above max threshold ({settings.PREBOOST_MAX_OUTDOOR_TEMP}°C).")


        if boost_mode == "preboost":
            self._state = "Pre-boost Expected"
            self._attributes["Pre-boost Expected"] = True
            _LOGGER.info("PumpSteerFutureStrategySensor: Pre-boost is expected based on forecast.")
        else:
            self._state = "Normal/Braking Expected"
            self._attributes["Pre-boost Expected"] = False
            _LOGGER.info("PumpSteerFutureStrategySensor: Pre-boost is NOT expected based on forecast.")


        # Update attributes for future strategy sensor
        self._attributes.update({
            "Cold Threshold Used": cold_threshold_for_future,
            "Price Threshold Ratio Used": price_threshold_ratio_for_future,
            "Lookahead Hours": lookahead_hours,
            "Forecast Temperature (next 6h)": hourly_temps_csv, # Raw CSV
            "Forecast Prices (next 6h)": electricity_prices,    # Raw list
        })
        _LOGGER.debug(f"PumpSteerFutureStrategySensor: Final state: {self._state}")
