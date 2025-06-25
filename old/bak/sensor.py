from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging
from datetime import datetime, timedelta

from .pre_boost import check_combined_preboost

_LOGGER = logging.getLogger(__name__)

# Constants for inertia calculation
INERTIA_UPDATE_INTERVAL = timedelta(minutes=10) # Hur ofta vi kollar delta
INERTIA_WEIGHT_FACTOR = 4 # Hur mycket gammal inertia ska väga
INERTIA_DIVISOR = 5 # (INERTIA_WEIGHT_FACTOR + 1)
MAX_INERTIA_VALUE = 5.0
MIN_INERTIA_VALUE = 0.0
DEFAULT_INERTIA_VALUE = 1.0

def safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def get_state(hass, entity_id):
    """Safely get the state of an entity."""
    entity = hass.states.get(entity_id)
    return entity.state if entity else None

def get_attr(hass, entity_id, attribute):
    """Safely get an attribute of an entity."""
    entity = hass.states.get(entity_id)
    return entity.attributes.get(attribute) if entity and attribute in entity.attributes else None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the PumpSteer sensor platform."""
    sensors = [PumpSteerSensor(hass, entry)]
    async_add_entities(sensors, True)

class PumpSteerSensor(Entity):
    """Representation of a PumpSteer Sensor."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry # Byt namn från _config till _config_entry för tydlighet
        self._state = None
        self._attributes = {}
        self._last_update_time = None
        self._previous_indoor_temp = None
        self._inertia_value = DEFAULT_INERTIA_VALUE
        self._name = "PumpSteer" # Standardnamn

        _LOGGER.debug(f"PumpSteerSensor: Initialiserar med config data: {self._config_entry.data}")
        _LOGGER.debug(f"PumpSteerSensor: Initialiserar med config options: {self._config_entry.options}")

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID to use for this sensor."""
        return f"pumpsteer_{self._config_entry.entry_id}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return self._attributes

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "°C"

    @property
    def device_class(self):
        """Return the device class."""
        return "temperature"

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:thermometer-lines"

    async def async_update(self):
        """Update the sensor."""
        # Hämta obligatoriska entiteter från config_entry.data
        indoor_temp_entity_id = self._config_entry.data.get("indoor_temp_entity")
        real_outdoor_entity_id = self._config_entry.data.get("real_outdoor_entity")
        electricity_price_entity_id = self._config_entry.data.get("electricity_price_entity")
        hourly_forecast_temps_entity_id = self._config_entry.data.get("hourly_forecast_temperatures_entity") # Nu från data!
        target_temp_entity_id = self._config_entry.data.get("target_temp_entity")
        summer_threshold_entity_id = self._config_entry.data.get("summer_threshold_entity")

        # Hämta valfria entiteter från config_entry.options
        aggressiveness_entity_id = self._config_entry.options.get("aggressiveness_entity")
        house_inertia_entity_id = self._config_entry.options.get("house_inertia_entity")

        # Hämta värden
        indoor_temp = safe_float(get_state(self.hass, indoor_temp_entity_id))
        real_outdoor_temp = safe_float(get_state(self.hass, real_outdoor_entity_id))
        electricity_prices = get_attr(self.hass, electricity_price_entity_id, "today")
        
        # Säkerhetskontroll för hourly_forecast_temps_entity_id är fortfarande relevant
        hourly_temps_csv = None
        if hourly_forecast_temps_entity_id: 
            hourly_temps_csv = get_state(self.hass, hourly_forecast_temps_entity_id)
        else:
            _LOGGER.warning("PumpSteer: 'hourly_forecast_temperatures_entity' är inte konfigurerad. Pre-boost kan vara inaktiv.")


        target_temp = safe_float(get_state(self.hass, target_temp_entity_id))
        summer_threshold_temp = safe_float(get_state(self.hass, summer_threshold_entity_id))
        
        _LOGGER.debug(f"PumpSteer: I async_update, hourly_forecast_temps_entity_id är: {hourly_forecast_temps_entity_id}")

        aggressiveness = safe_float(get_state(self.hass, aggressiveness_entity_id)) if aggressiveness_entity_id else None
        user_defined_inertia = safe_float(get_state(self.hass, house_inertia_entity_id)) if house_inertia_entity_id else None

        # Logga saknade data för felsökning
        # Notera: hourly_temps_csv kan vara None om entiteten inte har uppdaterats ännu,
        # men de andra bör vara satta om config_flow fungerar som det ska.
        if any(v is None for v in [indoor_temp, real_outdoor_temp, electricity_prices, target_temp, summer_threshold_temp]):
            _LOGGER.warning("PumpSteer: En eller flera nödvändiga entiteter saknar data: "
                            f"Inne: {indoor_temp}, Ute: {real_outdoor_temp}, Priser: {electricity_prices}, "
                            f"Måltemp: {target_temp}, Sommartröskel: {summer_threshold_temp}")
            self._state = None
            return

        # Uppdatera inertia om tillräckligt med tid har gått
        current_time = datetime.now()
        if self._last_update_time and (current_time - self._last_update_time) >= INERTIA_UPDATE_INTERVAL:
            if self._previous_indoor_temp is not None:
                temp_delta = indoor_temp - self._previous_indoor_temp
                adjusted_inertia = DEFAULT_INERTIA_VALUE - (temp_delta * 0.5)
                self._inertia_value = (self._inertia_value * INERTIA_WEIGHT_FACTOR + adjusted_inertia) / INERTIA_DIVISOR
                self._inertia_value = max(MIN_INERTIA_VALUE, min(MAX_INERTIA_VALUE, self._inertia_value))
            self._previous_indoor_temp = indoor_temp
            self._last_update_time = current_time
        elif not self._last_update_time:
            self._last_update_time = current_time
            self._previous_indoor_temp = indoor_temp

        # Använd användardefinierad inertia om tillgänglig, annars den beräknade
        current_inertia = user_defined_inertia if user_defined_inertia is not None else self._inertia_value

        # Logga för felsökning
        _LOGGER.debug(f"PumpSteer: Indoor Temp: {indoor_temp}°C, Real Outdoor Temp: {real_outdoor_temp}°C, "
                      f"Target Temp: {target_temp}°C, Summer Threshold: {summer_threshold_temp}°C, "
                      f"Aggressiveness: {aggressiveness}, Current Inertia: {current_inertia:.2f}")

        # Bestäm scaling_factor baserat på aggressivitet
        scaling_factor = 2.0
        if aggressiveness is not None:
            scaling_factor = 1.0 + (aggressiveness * 0.5)

        # --- Logik för PumpSteer ---

        # 1. Sommar-läge (högsta prioritet)
        if real_outdoor_temp >= summer_threshold_temp:
            self._state = 25.0
            self._attributes["Läge"] = "summer_mode"
            _LOGGER.info("PumpSteer: Summer Mode activated (Outdoor temp: %.1f >= %.1f)", real_outdoor_temp, summer_threshold_temp)
            self._attributes["Ute (verklig)"] = real_outdoor_temp
            self._attributes["Inne (mål)"] = target_temp
            self._attributes["Inne (verklig)"] = indoor_temp
            self._attributes["Inertia"] = round(current_inertia, 2)
            self._attributes["Aggressivitet"] = aggressiveness if aggressiveness is not None else "N/A"
            self._attributes["Sommartröskel"] = summer_threshold_temp
            self._attributes["Elpriser (prognos)"] = electricity_prices
            self._attributes["Väderprognos (text)"] = hourly_temps_csv
            return

        # 2. Pre-boost (andra prioritet, om väderprognos och elpriser finns)
        preboost_active = False
        if hourly_temps_csv and electricity_prices:
            try:
                lookahead_hours = 6
                cold_threshold = 2.0
                price_threshold_ratio = 0.8
                min_peak_hits = 1

                preboost_active = check_combined_preboost(
                    hourly_temps_csv,
                    electricity_prices,
                    lookahead_hours,
                    cold_threshold,
                    price_threshold_ratio,
                    min_peak_hits
                )
            except Exception as e:
                _LOGGER.error(f"PumpSteer: Fel vid beräkning av preboost: {e}")
                preboost_active = False

        if preboost_active:
            self._state = -15.0
            self._attributes["Läge"] = "preboost"
            _LOGGER.info("PumpSteer: Preboost activated")
        else:
            # 3. Normal drift (om ingen pre-boost eller sommar-läge)
            diff = indoor_temp - target_temp

            fake_temp = real_outdoor_temp + (diff * scaling_factor)

            if diff < 0:
                fake_temp = min(fake_temp, 20.0)
                _LOGGER.info("PumpSteer: Adjusted output (fake temp: %.1f °C, diff: %.2f) - Heating", fake_temp, diff)
                self._attributes["Läge"] = "balance"
            else:
                _LOGGER.info("PumpSteer: Adjusted output (fake temp: %.1f °C, diff: %.2f) - Braking/Neutral", fake_temp, diff)
                if abs(diff) < 0.5:
                    self._attributes["Läge"] = "neutral"
                else:
                    self._attributes["Läge"] = "balance"

            self._state = round(fake_temp, 1)

        # Uppdatera attribut oavsett läge
        self._attributes["Ute (verklig)"] = real_outdoor_temp
        self._attributes["Inne (mål)"] = target_temp
        self._attributes["Inne (verklig)"] = indoor_temp
        self._attributes["Inertia"] = round(current_inertia, 2)
        self._attributes["Aggressivitet"] = aggressiveness if aggressiveness is not None else "N/A"
        self._attributes["Sommartröskel"] = summer_threshold_temp
        self._attributes["Elpriser (prognos)"] = electricity_prices
        self._attributes["Väderprognos (text)"] = hourly_temps_csv
        _LOGGER.debug(f"PumpSteer: Final state: {self._state}°C, Mode: {self._attributes['Läge']}")
