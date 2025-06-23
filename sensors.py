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
    entity = hass.states.get(entity_id)
    return entity.state if entity else None

def get_attr(hass, entity_id, attribute):
    entity = hass.states.get(entity_id)
    return entity.attributes.get(attribute) if entity and attribute in entity.attributes else None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    sensors = [VirtualOutdoorTempSensor(hass, entry)]
    async_add_entities(sensors, True)

class VirtualOutdoorTempSensor(Entity):
    def __init__(self, hass, entry):
        self.hass = hass
        self._entry = entry
        self._state = None
        self._attributes = {}
        
        # Variabler för tröghetsberäkning
        self._last_inertia_update = None
        self._old_indoor_temp = None # Här lagrar vi den "gamla" inomhustemperaturen

    async def async_update(self):
        data = self._entry.options or self._entry.data

        indoor_entity = data.get("indoor_temp_entity")
        outdoor_entity = data.get("real_outdoor_entity")
        electricity_price_entity = data.get("electricity_price_entity")
        weather_entity = data.get("weather_entity")
        target_entity = data.get("target_temp_entity")

        # Hämta nuvarande värden
        indoor = safe_float(get_state(self.hass, indoor_entity))
        forecast_temp = safe_float(get_attr(self.hass, weather_entity, "temperature"))
        real_outdoor_temp = safe_float(get_state(self.hass, outdoor_entity))
        price = safe_float(get_state(self.hass, electricity_price_entity))
        target = safe_float(get_state(self.hass, target_entity))

        summer_threshold = safe_float(get_state(self.hass, "input_number.virtualoutdoortemp_summer_threshold"))
        
        # Hämta den aktuella trögheten från input_number
        current_inertia_entity = self.hass.states.get("input_number.house_inertia")
        current_inertia = safe_float(current_inertia_entity.state) if current_inertia_entity and current_inertia_entity.state not in ["unknown", "unavailable"] else DEFAULT_INERTIA_VALUE

        self._attributes = {
            "indoor_temperature": indoor,
            "target_temperature": target,
            "electricity_price": price,
            "real_outdoor_temperature": real_outdoor_temp,
            "summer_mode_threshold": summer_threshold,
            "house_inertia": current_inertia # Lägg till inertia som attribut
        }

        if None in (indoor, target, price, forecast_temp, real_outdoor_temp):
            self._state = "unavailable"
            _LOGGER.warning("VirtualOutdoorTemp: Waiting for all sensors to be ready.")
            return

        # --- Logik för beräkning av House Inertia ---
        now = datetime.now()
        if self._last_inertia_update is None or (now - self._last_inertia_update) >= INERTIA_UPDATE_INTERVAL:
            if self._old_indoor_temp is not None:
                # Beräkna delta baserat på FAKTISK inomhustemperatur
                indoor_temp_delta = (indoor - self._old_indoor_temp) 
                
                # Här kan du behöva justera hur delta används för inertia.
                # En positiv delta vid värmning (kallt ute) kan indikera låg tröghet.
                # En negativ delta vid kylning (varmt ute) kan indikera låg tröghet.
                # Denna beräkning är mer komplex och beror på värmepumpens tillstånd.
                # För enkelhetens skull behåller vi den nuvarande viktade medelvärdeslogiken,
                # men tänk på att delta kan behöva normaliseras eller tolkas annorlunda.

                # Exempel: Om delta är stor, kanske trögheten är låg?
                # Ett enkelt antagande: större temperaturförändring = lägre tröghet
                # För att hålla det likt din YAML, använder vi delta direkt men du kan justera detta.
                new_inertia_value = ((current_inertia * INERTIA_WEIGHT_FACTOR) + abs(indoor_temp_delta)) / INERTIA_DIVISOR
                
                # Begränsa tröghetsvärdet
                new_inertia_value = max(MIN_INERTIA_VALUE, min(new_inertia_value, MAX_INERTIA_VALUE))
                
                # Uppdatera input_number.house_inertia
                if current_inertia_entity:
                    await self.hass.services.async_call(
                        "input_number", 
                        "set_value", 
                        {"entity_id": "input_number.house_inertia", "value": round(new_inertia_value, 2)},
                        blocking=True # Vänta tills tjänsten är klar
                    )
                    _LOGGER.debug("VirtualOutdoorTemp: Updated House Inertia to %.2f (Delta: %.2f)", new_inertia_value, indoor_temp_delta)
                else:
                    _LOGGER.warning("VirtualOutdoorTemp: input_number.house_inertia not found, cannot update inertia.")

            self._old_indoor_temp = indoor # Uppdatera det gamla värdet
            self._last_inertia_update = now # Uppdatera tidstämpeln
        # --- Slut på tröghetsberäkning ---


        # Summer threshold override
        if summer_threshold is not None and real_outdoor_temp is not None:
            if real_outdoor_temp > summer_threshold:
                self._state = 20.0 # Standardvärde för sommarläge/ingen uppvärmning
                self._attributes["mode"] = "summer_threshold_mode"
                _LOGGER.info("VirtualOutdoorTemp: Summer threshold override active")
                return

        diff = target - indoor
        within_range = abs(diff) <= 0.5
        adjusted_diff = diff

        raw_temps = get_state(self.hass, "input_text.hourly_forecast_temperatures")
        if raw_temps:
            should_preboost = check_combined_preboost(raw_temps, [price], min_peak_hits=2)
            if should_preboost:
                preboost_max_temp = 20.0 
                fake_temp = max(real_outdoor_temp - 6, preboost_max_temp) 
                self._state = round(fake_temp, 1)
                self._attributes["mode"] = "preboost"
                _LOGGER.info("VirtualOutdoorTemp: Preboost active (fake temp: %.1f °C)", fake_temp)
                return

        if within_range:
            self._state = min(real_outdoor_temp, 20.0) 
            self._attributes["mode"] = "neutral"
            _LOGGER.info("VirtualOutdoorTemp: Neutral (within tolerance)")
        else:
            aggressiveness_entity = self.hass.states.get("input_number.virtualoutdoortemp_aggressiveness")
            aggressiveness = float(aggressiveness_entity.state) if aggressiveness_entity and aggressiveness_entity.state not in ["unknown", "unavailable"] else 0
            
            # Använd den redan hämtade och uppdaterade trögheten
            inertia = current_inertia # Använder det nyligen beräknade/hämtade värdet
            
            scaling_factor = (aggressiveness / 5) * 2 * (1 / inertia)

            max_virtual_temp_for_heating_modes = 20.0 

            fake_temp = real_outdoor_temp - adjusted_diff * scaling_factor
            
            fake_temp = min(fake_temp, max_virtual_temp_for_heating_modes)

            self._state = round(fake_temp, 1)
            self._attributes.update({
                "difference_to_target": round(diff, 2),
                "aggressiveness": aggressiveness,
                "scaling_factor": round(scaling_factor, 2),
                "mode": "balance"
            })
            _LOGGER.info("VirtualOutdoorTemp: Adjusted output (fake temp: %.1f °C, diff: %.2f)", fake_temp, diff)

    @property
    def name(self):
        return "VirtualOutdoorTemp"

    @property
    def state(self):
        return self._state

    @property
    def unique_id(self):
        return "virtual_outdoor_temp"

    @property
    def device_class(self):
        return "temperature"

    @property
    def unit_of_measurement(self):
        return "°C"

    @property
    def state_class(self):
        return "measurement"

    @property
    def extra_state_attributes(self):
        return self._attributes
