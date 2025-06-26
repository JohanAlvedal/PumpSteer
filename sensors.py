# Standardimporter
import logging
from datetime import datetime, timedelta

# Home Assistant-specifika importer
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
# ÅTERSTÄLLD IMPORT FÖR ATT FÖLJA DITT ORIGINAL OCH UNDVIKA KOMPATIBILITETSPROBLEM
# 'device_class' och 'state_class' sätts som strängar, vilket fungerar i din miljö.
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN # Dessa importer är korrekta och fungerar.


# Importera async_call_later för att kunna schemalägga om uppdateringar
from homeassistant.helpers.event import async_call_later

# Anpassade importer för PumpSteer
from .pre_boost import check_combined_preboost

_LOGGER = logging.getLogger(__name__)

# Konstanter för tröghetsberäkning
INERTIA_UPDATE_INTERVAL = timedelta(minutes=10) # Hur ofta vi kollar delta
INERTIA_WEIGHT_FACTOR = 4 # Hur mycket gammal inertia ska väga
INERTIA_DIVISOR = 5 # (INERTIA_WEIGHT_FACTOR + 1)
MAX_INERTIA_VALUE = 5.0
MIN_INERTIA_VALUE = 0.0
DEFAULT_INERTIA_VALUE = 1.0

# Hårdkodad konstant för pre-boost temperaturgräns.
PREBOOST_MAX_OUTDOOR_TEMP = 10.0

def safe_float(val):
    """Konverterar ett värde säkert till float, returnerar None vid fel."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def get_state(hass, entity_id):
    """Hämtar tillståndet för en entitet säkert. Returnerar None om entity_id är ogiltigt eller tillståndet är unavailable/unknown."""
    if not entity_id:
        return None
    entity = hass.states.get(entity_id)
    if entity and entity.state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
        return entity.state
    return None

def get_attr(hass, entity_id, attribute):
    """Hämtar ett attribut från en entitet säkert. Returnerar None om entity_id är ogiltigt eller attributet saknas."""
    if not entity_id:
        return None
    entity = hass.states.get(entity_id)
    return entity.attributes.get(attribute) if entity and attribute in entity.attributes else None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Sätter upp PumpSteer sensor-plattformen."""
    sensors = [PumpSteerSensor(hass, entry)]
    async_add_entities(sensors, True)

class PumpSteerSensor(Entity):
    """Representation av en PumpSteer Sensor."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry
        self._state = None
        self._attributes = {}
        self._last_update_time = None
        self._previous_indoor_temp = None
        self._last_outdoor_temp = None # Initialisera även denna för tröghetsberäkning
        self._inertia_value = DEFAULT_INERTIA_VALUE
        self._name = "PumpSteer"

        # Sätt standard Home Assistant egenskaper - ÅTERGÅR TILL STRÄNGAR FÖR KOMPATIBILITET
        self._attr_unit_of_measurement = "°C"
        self._attr_device_class = "temperature" # Ändrad tillbaka till sträng för kompatibilitet
        self._attr_state_class = "measurement" # Ändrad tillbaka till sträng för kompatibilitet
        self._attr_unique_id = config_entry.entry_id

        # Initiera extra attribut
        self._attributes = {
            "Status": "Initialiserar",
            "Läge": "initialiserar",
            "Ute (verklig)": None,
            "Inne (mål)": None,
            "Inne (verklig)": None,
            "Inertia": self._inertia_value,
            "Aggressivitet": None,
            "Sommartröskel": None,
            "Elpriser (prognos)": None,
            "Pre-boost Aktiv": False,
        }

        # Lägg till en lyssnare för konfigurationsändringar
        config_entry.add_update_listener(self.async_options_update_listener)

        _LOGGER.debug(f"PumpSteerSensor: Initialiserar med config data: {self._config_entry.data}")
        _LOGGER.debug(f"PumpSteerSensor: Initialiserar med config options: {self._config_entry.options}")

    @property
    def name(self):
        """Returnerar sensorns namn."""
        return self._name

    @property
    def unique_id(self):
        """Returnerar ett unikt ID för sensorn."""
        return f"pumpsteer_{self._config_entry.entry_id}"

    @property
    def state(self):
        """Returnerar sensorns tillstånd."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Returnerar sensorns tillståndsattribut."""
        return self._attributes

    @property
    def unit_of_measurement(self):
        """Returnerar enheten för mätning."""
        return "°C"

    @property
    def device_class(self):
        """Returnerar enhetsklassen."""
        return "temperature" # Fortsätt att returnera sträng för kompatibilitet

    @property
    def icon(self):
        """Returnerar ikonen att använda i frontend."""
        return "mdi:thermometer-lines"

    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry):
        """Hanterar uppdatering av alternativ."""
        _LOGGER.debug("PumpSteer: Alternativ uppdaterade, laddar om sensor.")
        self._config_entry = entry
        await self.async_update()

    async def async_update(self):
        """Uppdaterar sensorns tillstånd."""
        config = {**self._config_entry.data, **self._config_entry.options}
        indoor_temp_entity_id = config.get("indoor_temp_entity")
        real_outdoor_entity_id = config.get("real_outdoor_entity")
        electricity_price_entity_id = config.get("electricity_price_entity")
        hourly_forecast_temps_entity_id = config.get("weather_entity")
        target_temp_entity_id = config.get("target_temp_entity")
        summer_threshold_entity_id = config.get("summer_threshold_entity")

        preboost_max_outdoor_temp = 10.0 # Konstanter hårdkodas direkt i funktionen om de inte är globala

        indoor_temp = safe_float(get_state(self.hass, indoor_temp_entity_id))
        real_outdoor_temp = safe_float(get_state(self.hass, real_outdoor_entity_id))
        electricity_prices = get_attr(self.hass, electricity_price_entity_id, "today")
        hourly_temps_csv = None
        if hourly_forecast_temps_entity_id:
            hourly_temps_csv = get_state(self.hass, hourly_forecast_temps_entity_id)
        
        target_temp = safe_float(get_state(self.hass, target_temp_entity_id))
        summer_threshold_temp = safe_float(get_state(self.hass, summer_threshold_entity_id))

        aggressiveness = safe_float(get_state(self.hass, "input_number.virtualoutdoortemp_aggressiveness"))
        if aggressiveness is None:
            aggressiveness = 0.0
            _LOGGER.warning("PumpSteer: Aggressiveness entity (input_number.virtualoutdoortemp_aggressiveness) is unavailable. Defaulting aggressiveness to 0.0.")

        user_defined_inertia = safe_float(get_state(self.hass, "input_number.house_inertia"))
        house_inertia_entity_id = "input_number.house_inertia"

        critical_entities_data = {
            "Inne (verklig)": indoor_temp,
            "Ute (verklig)": real_outdoor_temp,
            "Måltemp": target_temp,
            "Sommartröskel": summer_threshold_temp,
        }

        missing_data_info = [name for name, value in critical_entities_data.items() if value is None]

        if missing_data_info:
            _LOGGER.warning("PumpSteer: Väntar på data för: %s. Försöker igen om 10 sekunder.", ", ".join(missing_data_info))
            self._state = STATE_UNAVAILABLE
            self._attributes["Status"] = f"Väntar på data: {', '.join(missing_data_info)}"

            self.async_on_remove(
                async_call_later(self.hass, timedelta(seconds=10), self.async_schedule_update_ha_state)
            )
            return

        self._attributes["Status"] = "OK"

        if real_outdoor_temp >= summer_threshold_temp:
            self._state = 25.0
            self._attributes["Läge"] = "summer_mode"
            self._attributes["Pre-boost Aktiv"] = False
            _LOGGER.info("PumpSteer: Summer Mode activated (Outdoor temp: %.1f >= %.1f)", real_outdoor_temp, summer_threshold_temp)
        else:
            boost_mode = None
            if hourly_temps_csv and electricity_prices:
                if real_outdoor_temp > preboost_max_outdoor_temp:
                    _LOGGER.info(f"PumpSteer: Pre-boost avaktiverat eftersom utomhustemperaturen ({real_outdoor_temp}°C) är över maxtröskeln ({preboost_max_outdoor_temp}°C).")
                else:
                    try:
                        # Anropa check_combined_preboost med aggressivitet
                        # Observera: Detta anrop förväntar sig den nya versionen av pre_boost.py
                        boost_mode = check_combined_preboost(
                            hourly_temps_csv,
                            electricity_prices,
                            lookahead_hours=6,
                            cold_threshold=2.0,
                            price_threshold_ratio=0.8,
                            min_peak_hits=1,
                            aggressiveness=aggressiveness
                        )
                    except Exception as e:
                        _LOGGER.error(f"PumpSteer: Fel vid beräkning av preboost: {e}", exc_info=True)
            
            if boost_mode == "preboost":
                self._state = -15.0
                self._attributes["Läge"] = "preboost"
                self._attributes["Pre-boost Aktiv"] = True
                _LOGGER.info("PumpSteer: Preboost (gasa) activated to build heat buffer.")
            elif boost_mode == "braking":
                self._state = 25.0
                self._attributes["Läge"] = "braking_mode"
                self._attributes["Pre-boost Aktiv"] = True
                _LOGGER.info("PumpSteer: Braking mode activated to save energy during peak price.")
            else:
                diff = indoor_temp - target_temp
                scaling_factor = aggressiveness * 0.5 
                _LOGGER.debug(f"PumpSteer: Aggressiveness: {aggressiveness}, Scaling Factor: {scaling_factor:.2f}")

                fake_temp = real_outdoor_temp + (diff * scaling_factor)

                if diff < 0:
                    fake_temp = min(fake_temp, 20.0)
                    self._attributes["Läge"] = "heating"
                else:
                    if abs(diff) < 0.5:
                        self._attributes["Läge"] = "neutral"
                    else:
                        self._attributes["Läge"] = "braking"
                        
                _LOGGER.info("PumpSteer: Normal operation (fake temp: %.1f °C, diff: %.2f) - Mode: %s", fake_temp, diff, self._attributes["Läge"])
                self._state = round(fake_temp, 1)
                self._attributes["Pre-boost Aktiv"] = False

        current_time = datetime.now()
        
        if self._last_update_time and (current_time - self._last_update_time) >= INERTIA_UPDATE_INTERVAL:
            if not self._attributes["Pre-boost Aktiv"]:
                if self._previous_indoor_temp is not None and self._last_outdoor_temp is not None:
                    delta_indoor = indoor_temp - self._previous_indoor_temp
                    delta_outdoor = real_outdoor_temp - self._last_outdoor_temp
                    if abs(delta_outdoor) > 0.001:
                        new_inertia_contribution = delta_indoor / delta_outdoor
                        new_inertia_contribution = max(-5.0, min(5.0, new_inertia_contribution))
                        
                        self._inertia_value = (self._inertia_value * INERTIA_WEIGHT_FACTOR + new_inertia_contribution) / INERTIA_DIVISOR
                        self._inertia_value = max(MIN_INERTIA_VALUE, min(MAX_INERTIA_VALUE, self._inertia_value))
                        
                        if house_inertia_entity_id:
                            await self.hass.services.async_call(
                                "input_number", "set_value",
                                {"entity_id": house_inertia_entity_id, "value": round(self._inertia_value, 2)},
                                blocking=False,
                            )
                            _LOGGER.debug(f"PumpSteer: Uppdaterade input_number.house_inertia till {self._inertia_value:.2f}")
                    else:
                        _LOGGER.debug("PumpSteer: Delta outdoor too small (%.2f), skipping inertia calculation for this interval.", delta_outdoor)
                else:
                    _LOGGER.debug("PumpSteer: Previous indoor/outdoor temp not available, skipping inertia calculation.")

                self._previous_indoor_temp = indoor_temp
                self._last_outdoor_temp = real_outdoor_temp
                self._last_update_time = current_time
            else:
                _LOGGER.info("Inertia-beräkning pausad på grund av Pre-boost/Braking-läge. Ingen uppdatering av inertia-värdet.")
                
        elif not self._last_update_time:
            self._last_update_time = current_time
            self._previous_indoor_temp = indoor_temp
            self._last_outdoor_temp = real_outdoor_temp

        current_inertia = user_defined_inertia if user_defined_inertia is not None else self._inertia_value

        self._attributes["Ute (verklig)"] = real_outdoor_temp
        self._attributes["Inne (mål)"] = target_temp
        self._attributes["Inne (verklig)"] = indoor_temp
        self._attributes["Inertia"] = round(current_inertia, 2)
        self._attributes["Aggressivitet"] = aggressiveness
        self._attributes["Sommartröskel"] = summer_threshold_temp
        self._attributes["Elpriser (prognos)"] = electricity_prices
        self._attributes["Pre-boost Aktiv"] = self._attributes.get("Pre-boost Aktiv", False)
        _LOGGER.debug(f"PumpSteer: Final state: {self._state}°C, Mode: {self._attributes['Läge']}")
