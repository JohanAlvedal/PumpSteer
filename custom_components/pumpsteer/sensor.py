# Standard imports
import logging
from datetime import datetime, timedelta

# Home Assistant-specific imports
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.typing import StateType # För typning av tillstånd

# Import async_call_later to schedule updates
from homeassistant.helpers.event import async_call_later

# Custom imports for PumpSteer
from .pre_boost import check_combined_preboost
from .holiday import is_holiday_mode_active, HOLIDAY_TARGET_TEMPERATURE

_LOGGER = logging.getLogger(__name__)

# Constants for inertia calculation
INERTIA_UPDATE_INTERVAL = timedelta(minutes=10) # How often we check delta
INERTIA_WEIGHT_FACTOR = 4 # How much old inertia should weigh
INERTIA_DIVISOR = 5 # (INERTIA_WEIGHT_FACTOR + 1)
MAX_INERTIA_VALUE = 5.0
MIN_INERTIA_VALUE = 0.0
DEFAULT_INERTIA_VALUE = 1.0
PREBOOST_MAX_OUTDOOR_TEMP = 10.0

def safe_float(val: StateType) -> float | None:
    """Safely converts a value to float, returns None on error."""
    try:
        if val is None: # Explicitly handle None
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
        self._inertia_value = DEFAULT_INERTIA_VALUE
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
            "Indoor (target)": None, # Kommer att uppdateras med actual_target_temp_for_logic
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
        self._config_entry = entry # Uppdatera config_entry för att få de senaste optionerna
        await self.async_update() # Anropa update direkt för att tillämpa nya inställningar

    async def async_update(self) -> None:
        """Updates the sensor's state."""
        # Kombinera data och options för att få den fullständiga konfigurationen
        config = {**self._config_entry.data, **self._config_entry.options}
        
        # Hämta alla entitets-ID:n från den kombinerade konfigurationen
        indoor_temp_entity_id = config.get("indoor_temp_entity")
        real_outdoor_temp_entity_id = config.get("real_outdoor_entity")
        electricity_price_entity_id = config.get("electricity_price_entity")
        hourly_forecast_temperatures_entity_id = config.get("hourly_forecast_temperatures_entity")
        target_temp_entity_id = config.get("target_temp_entity")
        summer_threshold_entity_id = config.get("summer_threshold_entity")
        
        # Hämta ID för semesterläges-hjälparna (de kan vara None om de är valfria och inte konfigurerade)
        holiday_mode_boolean_entity_id = self._config_entry.options.get("holiday_mode_boolean_entity") or config.get("holiday_mode_boolean_entity")
        holiday_start_datetime_entity_id = self._config_entry.options.get("holiday_start_datetime_entity") or config.get("holiday_start_datetime_entity")
        holiday_end_datetime_entity_id = self._config_entry.options.get("holiday_end_datetime_entity") or config.get("holiday_end_datetime_entity")

        # Hämta tillstånd för entiteter
        indoor_temp = safe_float(get_state(self.hass, indoor_temp_entity_id))
        real_outdoor_temp = safe_float(get_state(self.hass, real_outdoor_temp_entity_id))
        electricity_prices = get_attr(self.hass, electricity_price_entity_id, "today") 
        hourly_temps_csv = get_state(self.hass, hourly_forecast_temperatures_entity_id)
        
        # Hämta måltemperatur och sommar-tröskel från input_number hjälpare
        configured_target_temp = safe_float(get_state(self.hass, target_temp_entity_id))
        summer_threshold_temp = safe_float(get_state(self.hass, summer_threshold_entity_id))
        
        # Aggressiveness och inertia från hjälpare (antar att de alltid finns)
        aggressiveness = safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or 0.0
        user_defined_inertia = safe_float(get_state(self.hass, "input_number.house_inertia")) 
        inertia = user_defined_inertia if user_defined_inertia is not None else self._inertia_value

        # Samla kritisk data för att kontrollera om något saknas
        critical_entities_data = {
            "Indoor (actual)": indoor_temp,
            "Outdoor (actual)": real_outdoor_temp,
            "Target Temp": configured_target_temp, # Använder det konfigurerade värdet här
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
        
        # --- LOGIK FÖR SEMESTERLÄGE ---
        # Kontrollera om semesterläget är aktivt
        holiday_mode_active = False
        if holiday_mode_boolean_entity_id and holiday_start_datetime_entity_id and holiday_end_datetime_entity_id:
            holiday_mode_active = is_holiday_mode_active(
                self.hass,
                holiday_mode_boolean_entity_id,
                holiday_start_datetime_entity_id,
                holiday_end_datetime_entity_id
            )
        
        # Bestäm den faktiska måltemperaturen att använda i beräkningarna
        # Standard är den konfigurerade temperaturen
        actual_target_temp_for_logic = configured_target_temp

        if holiday_mode_active:
            actual_target_temp_for_logic = HOLIDAY_TARGET_TEMPERATURE
            self._attributes["Mode"] = "Holiday"
            _LOGGER.info(f"[PumpSteer] Overriding target temperature to {HOLIDAY_TARGET_TEMPERATURE}°C due to Holiday Mode.")
        elif self._attributes.get("Mode") == "Holiday": # Om vi precis lämnat semesterläge
             self._attributes["Mode"] = "Normal" # Återställ till Normal (eller vad standard är)

        # --- SLUT LOGIK FÖR SEMESTERLÄGE ---


        # --- CHECK MODE AND SET OUTPUT VALUE ---
        
        # 1. Summer Mode - highest priority (still uses actual_target_temp_for_logic for logic)
        if real_outdoor_temp >= summer_threshold_temp:
            self._state = round(25.0, 1) # Högt värde för att stänga av/minimera värmen
            self._attributes["Mode"] = "summer_mode" + (" + holiday" if holiday_mode_active else "")
            self._attributes["Pre-boost Active"] = False
            _LOGGER.info("PumpSteer: Summer Mode activated (Outdoor temp: %.1f >= %.1f)", real_outdoor_temp, summer_threshold_temp)
        elif holiday_mode_active: # Semesterläge har redan hanterats ovan och satt Mode till "Holiday"
            # Ingen ytterligare logik här, state sätts i slutet baserat på actual_target_temp_for_logic
            pass
        else: # Endast om inte sommarläge eller semesterläge är aktivt
            # 2. Braking Mode (based on price) - prioritized over pre-boost
            max_price_in_forecast = max(electricity_prices) if electricity_prices else 0.0
            current_price = electricity_prices[0] if electricity_prices and electricity_prices[0] is not None else 0.0

            price_factor = 0.0
            if max_price_in_forecast > 0:
                price_factor = current_price / max_price_in_forecast
            
            # Dynamic threshold based on aggressiveness
            braking_threshold_ratio = 1.0 - (aggressiveness / 5.0) * 0.4 
            
            if price_factor >= braking_threshold_ratio:
                self._state = round(25.0, 1) # Sets the virtual outdoor temperature to a high level
                self._attributes["Mode"] = "braking_mode"
                self._attributes["Pre-boost Active"] = True # Use this to pause inertia calculation
                _LOGGER.info("PumpSteer: Braking mode activated due to high price (Aggressiveness: %.1f, Price Factor: %.2f)", aggressiveness, price_factor)
            else:
                # 3. Pre-boost Mode (based on forecast)
                boost_mode = None
                if real_outdoor_temp <= PREBOOST_MAX_OUTDOOR_TEMP:
                    # Använd actual_target_temp_for_logic för cold_threshold om det behövs i check_combined_preboost
                    # (cold_threshold i pre_boost.py är just nu en fast parameter, men om den ska vara dynamisk)
                    boost_mode = check_combined_preboost(
                        hourly_temps_csv,
                        electricity_prices,
                        lookahead_hours=6,
                        cold_threshold=actual_target_temp_for_logic - 2.0, # Exempel: 2 grader under måltemperaturen
                        price_threshold_ratio=0.8,
                        aggressiveness=aggressiveness, 
                        inertia=inertia
                    )
                else:
                    _LOGGER.info(f"PumpSteer: Pre-boost deactivated as outdoor temperature ({real_outdoor_temp}°C) is above max threshold ({PREBOOST_MAX_OUTDOOR_TEMP}°C).")
                
                if boost_mode == "preboost":
                    self._state = -15.0 # Very low virtual outdoor temp to accelerate
                    self._attributes["Mode"] = "preboost"
                    self._attributes["Pre-boost Active"] = True
                    _LOGGER.info("PumpSteer: Preboost (accelerate) activated to build heat buffer.")
                else:
                    # 4. Normal operation (heating/neutral)
                    # Denna logik MÅSTE använda actual_target_temp_for_logic
                    diff = indoor_temp - actual_target_temp_for_logic # <--- ANVÄND actual_target_temp_for_logic
                    
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
        
        # Tröghetsberäkningen pausas om Pre-boost eller Braking är aktivt.
        # Vi använder attributet "Pre-boost Active" som ett generellt flagga för detta.
        if self._last_update_time and (current_time - self._last_update_time) >= INERTIA_UPDATE_INTERVAL:
            if not self._attributes.get("Pre-boost Active") and not self._attributes.get("Mode") == "braking_mode" and not self._attributes.get("Mode") == "summer_mode" and not self._attributes.get("Mode") == "Holiday":
                 # Endast utför tröghetsberäkning i "Normal" eller "heating/neutral" läge
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

        current_inertia = user_defined_inertia if user_defined_inertia is not None else self._inertia_value

        # Uppdatera attributen
        self._attributes.update({
            "Outdoor (actual)": real_outdoor_temp,
            "Indoor (target)": actual_target_temp_for_logic, # <--- Visar den faktiska måltempen som används
            "Indoor (actual)": indoor_temp,
            "Inertia": round(current_inertia, 2),
            "Aggressiveness": aggressiveness,
            "Summer Threshold": summer_threshold_temp,
            "Electricity Prices (forecast)": electricity_prices,
            "Pre-boost Active": self._attributes.get("Pre-boost Active", False),
            # "Mode" sätts redan i if/elif-satserna ovan
        })
        _LOGGER.debug(f"PumpSteer: Final state: {self._state}°C, Mode: {self._attributes['Mode']}")


class PumpSteerFutureStrategySensor(Entity):
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry
        self._state = 0
        self._attributes = {}
        self._name = "PumpSteer Future Strategy"
        self._attr_unique_id = f"{config_entry.entry_id}_future_strategy"

    @property
    def name(self): return self._name
    @property
    def unique_id(self): return self._attr_unique_id

    @property
    def state(self):
        return self._state if self._state is not None else 0

    @property
    def extra_state_attributes(self):
        return {
            **self._attributes,
            "friendly_name": "PumpSteer – Forecast Strategy"
        }

    @property
    def icon(self): return "mdi:timeline-clock"

    async def async_update(self):
        config = {**self._config_entry.data, **self._config_entry.options}
        temps_csv = get_state(self.hass, config.get("hourly_forecast_temperatures_entity"))
        prices = get_attr(self.hass, config.get("electricity_price_entity"), "today") 
        aggressiveness = safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or 0.0
        inertia = safe_float(get_state(self.hass, "input_number.house_inertia")) or 1.0
        
        lookahead_hours = 6

        if not temps_csv or not prices or len(prices) < lookahead_hours:
            self._attributes = {"strategy_status": "forecast data missing or incomplete"}
            self._state = None
            return

        try:
            temps = [float(t.strip()) for t in temps_csv.split(",") if t.strip()]
            if len(temps) < lookahead_hours:
                self._attributes = {"strategy_status": "incomplete temperature forecast data"}
                self._state = None
                return
        except Exception:
            self._attributes = {"strategy_status": "invalid temperature format"}
            self._state = None
            return

        # --- FUTURE STRATEGY CALCULATION ---
        
        # 1. Pre-boost logic (cold + expensive)
        cold_threshold = 2.0 # Denna kan vara fast eller dynamisk baserat på actual_target_temp_for_logic om du vill
        adjusted_price_threshold_ratio = max(0.5, min(0.9, 0.9 - aggressiveness * 0.04))
        max_price = max(prices[:lookahead_hours]) if prices else 0.0
        preboost_price_threshold = max_price * adjusted_price_threshold_ratio
        
        lead_time = min(3.0, max(0.5, inertia * 0.75))
        next_preboost_hour = None
        cold_expensive_matches = 0

        for i in range(1, lookahead_hours):
            if temps[i] < cold_threshold and prices[i] >= preboost_price_threshold:
                cold_expensive_matches += 1
                if i <= round(lead_time) and not next_preboost_hour:
                    future_hour = datetime.now() + timedelta(hours=i)
                    next_preboost_hour = future_hour.strftime("%H:00")
        
        # 2. Braking logic (just expensive)
        braking_threshold_ratio = 1.0 - (aggressiveness / 5.0) * 0.4
        braking_price_threshold = max_price * braking_threshold_ratio
        
        expensive_hours_count = 0
        
        for i in range(lookahead_hours):
            if prices[i] >= braking_price_threshold:
                expensive_hours_count += 1

        # Update sensor state and attributes
        self._state = cold_expensive_matches
        self._attributes = {
            "strategy_status": "ok",
            "preboost_expected_in_hours": round(lead_time),
            "first_preboost_hour": next_preboost_hour,
            "cold_and_expensive_hours_next_6h": cold_expensive_matches,
            "expensive_hours_next_6h": expensive_hours_count,
            "braking_price_threshold_percent": round(braking_threshold_ratio * 100),
            "preboost_active": False 
        }
