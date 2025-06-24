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
    def __init__(self, hass: HomeAssistant, config: ConfigEntry):
        self.hass = hass
        self._config = config.data # Använd .data för att hämta konfigurationen
        self._state = None
        self._attributes = {}
        self.last_update_time = None
        self.last_indoor_temp = None
        self.last_outdoor_temp = None
        self.current_inertia = DEFAULT_INERTIA_VALUE # Initiera med standardvärde
        self.inertia_update_time = None

    @property
    def name(self):
        return "VirtualOutdoorTemp"

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
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        indoor_temp_entity_id = self._config.get("indoor_temp_entity")
        real_outdoor_entity_id = self._config.get("real_outdoor_entity")
        electricity_price_entity_id = self._config.get("electricity_price_entity")
        weather_entity_id = self._config.get("weather_entity")
        target_temp_entity_id = self._config.get("target_temp_entity")
        summer_threshold_entity_id = self._config.get("summer_threshold_entity") # NY KONFIGURATION

        # --- Hämta och parsa rådata från sensorer ---
        indoor_temp_str = get_state(self.hass, indoor_temp_entity_id)
        indoor_temp = safe_float(indoor_temp_str)
        _LOGGER.debug(f"VirtualOutdoorTemp: Indoor temp raw: '{indoor_temp_str}', parsed: {indoor_temp}")

        target_temp_str = get_state(self.hass, target_temp_entity_id)
        target_temp = safe_float(target_temp_str)
        _LOGGER.debug(f"VirtualOutdoorTemp: Target temp raw: '{target_temp_str}', parsed: {target_temp}")

        real_outdoor_temp_str = get_state(self.hass, real_outdoor_entity_id)
        real_outdoor_temp = safe_float(real_outdoor_temp_str)
        _LOGGER.debug(f"VirtualOutdoorTemp: Real outdoor temp raw: '{real_outdoor_temp_str}', parsed: {real_outdoor_temp}")

        current_electricity_price_str = get_state(self.hass, electricity_price_entity_id)
        current_electricity_price = safe_float(current_electricity_price_str)
        _LOGGER.debug(f"VirtualOutdoorTemp: Current electricity price raw: '{current_electricity_price_str}', parsed: {current_electricity_price}")

        # Hämta aggressivitet (vi har ingen input för detta i config_flow just nu, så vi sätter ett default)
        # Antag att aggressiveness_entity_id är hårdkodad eller kommer från en framtida konfiguration
        aggressiveness_entity_id = "input_number.virtualoutdoortemp_aggressiveness"
        aggressiveness_str = get_state(self.hass, aggressiveness_entity_id)
        aggressiveness = safe_float(aggressiveness_str)
        _LOGGER.debug(f"VirtualOutdoorTemp: Aggressiveness raw: '{aggressiveness_str}', parsed: {aggressiveness}")
        if aggressiveness is None:
            _LOGGER.warning("VirtualOutdoorTemp: Aggressiveness entity is unavailable or not a number. Using default 1.0.")
            aggressiveness = DEFAULT_INERTIA_VALUE # Se till att aggressiveness alltid är ett nummer


        # Kontrollera att nödvändiga grundläggande sensorer är tillgängliga
        if indoor_temp is None or target_temp is None or real_outdoor_temp is None:
            _LOGGER.warning("VirtualOutdoorTemp: En eller flera av de nödvändiga grundläggande sensorerna är otillgängliga eller inte nummer.")
            self._state = None # Sätt tillstånd till None om data saknas
            self._attributes = {
                "Innetemp": indoor_temp,
                "Måltemp": target_temp,
                "Elpris": current_electricity_price,
                "Ute (verklig)": real_outdoor_temp,
                "Sommartröskel": None, # Ingen sommartröskel om grunddata saknas
                "Tröghet": None, # Ingen tröghet om grunddata saknas
                "Delta till mål": None,
                "Aggressivitet": None,
                "scaling_factor": None,
                "Läge": "unavailable",
                "Virtuell UteTemp": None
            }
            return

        # --- Beräkna Delta till mål ---
        # Positiv diff = för varmt inne (vill bromsa värme)
        # Negativ diff = för kallt inne (vill öka värme)
        diff = indoor_temp - target_temp

        # --- Logik för beräkning av House Inertia ---
        now = datetime.now()
        if self.last_update_time is not None and (now - self.last_update_time) >= INERTIA_UPDATE_INTERVAL:
            if self.last_indoor_temp is not None and self.last_outdoor_temp is not None and real_outdoor_temp is not None:
                # Beräkna förändringar
                delta_indoor = indoor_temp - self.last_indoor_temp
                delta_outdoor = real_outdoor_temp - self.last_outdoor_temp
                
                # För att undvika division med noll eller instabila beräkningar om delta_outdoor är för litet
                if abs(delta_outdoor) > 0.1: # Kräver en viss förändring i utomhustemperaturen
                    # En enkel modell för tröghet: hur mycket innetemperaturen förändras
                    # i förhållande till utomhustemperaturens förändring över tid.
                    # Mindre delta_indoor för ett givet delta_outdoor indikerar högre tröghet.
                    # Här använder vi en omvänd relation: ett stort delta_indoor för ett litet delta_outdoor indikerar låg tröghet.
                    # Dvs, hur mycket innetemperaturen "följer" utomhustemperaturen
                    # Ju mindre kvot, desto högre tröghet (innetempen ändras mindre än ute)
                    calculated_inertia = 1.0 - (delta_indoor / delta_outdoor) if delta_outdoor != 0 else 1.0
                    
                    # Begränsa calculated_inertia till ett rimligt intervall
                    calculated_inertia = max(MIN_INERTIA_VALUE, min(MAX_INERTIA_VALUE, calculated_inertia))

                    # Uppdatera self.current_inertia med ett viktat medelvärde
                    self.current_inertia = (self.current_inertia * INERTIA_WEIGHT_FACTOR + calculated_inertia) / INERTIA_DIVISOR
                    _LOGGER.debug(f"VirtualOutdoorTemp: Inertia updated. Delta Indoor: {delta_indoor:.2f}, Delta Outdoor: {delta_outdoor:.2f}, Calculated Inertia: {calculated_inertia:.2f}, Current Weighted Inertia: {self.current_inertia:.2f}")
                else:
                    _LOGGER.debug("VirtualOutdoorTemp: Skipping inertia update due to small outdoor temperature change.")
            else:
                _LOGGER.debug("VirtualOutdoorTemp: Not enough historical data for inertia calculation yet.")

            # Uppdatera senaste värden efter varje beräkning (eller efter intervall)
            self.last_indoor_temp = indoor_temp
            self.last_outdoor_temp = real_outdoor_temp
            self.last_update_time = now
        elif self.last_update_time is None:
            # Första körningen, initiera värden
            self.last_indoor_temp = indoor_temp
            self.last_outdoor_temp = real_outdoor_temp
            self.last_update_time = now
            _LOGGER.debug("VirtualOutdoorTemp: Initializing last known temperatures for inertia calculation.")
        else:
            _LOGGER.debug(f"VirtualOutdoorTemp: Inertia update skipped. Next update in {(INERTIA_UPDATE_INTERVAL - (now - self.last_update_time)).total_seconds():.0f} seconds.")

        # Hämta värde från input_number.house_inertia om den finns, annars använd den beräknade
        house_inertia_input_id = "input_number.house_inertia" # Detta ID måste skapas av användaren
        house_inertia_input_str = get_state(self.hass, house_inertia_input_id)
        house_inertia_from_input = safe_float(house_inertia_input_str)
        _LOGGER.debug(f"VirtualOutdoorTemp: House Inertia Input raw: '{house_inertia_input_str}', parsed: {house_inertia_from_input}")

        if house_inertia_from_input is not None:
            current_inertia = house_inertia_from_input
            _LOGGER.debug(f"VirtualOutdoorTemp: Using user-defined House Inertia: {current_inertia}")
        else:
            current_inertia = self.current_inertia # Använd den beräknade trögheten om ingen input_number finns
            _LOGGER.warning("VirtualOutdoorTemp: User-defined House inertia (input_number.house_inertia) is unavailable or not a number. Using calculated inertia or default.")

        # --- Hämta framtida temperaturer för pre-boost ---
        # Nu hämtar vi från input_text.hourly_forecast_temperatures state
        raw_temps_str = get_state(self.hass, weather_entity_id) # <-- HÄMTAR STATE
        future_temps = []
        if raw_temps_str:
            try:
                # Splitta strängen och konvertera till float
                future_temps = [safe_float(t.strip()) for t in raw_temps_str.split(',') if safe_float(t.strip()) is not None]
                future_temps_csv = ",".join(map(str, future_temps))
            except Exception as e:
                _LOGGER.warning(f"VirtualOutdoorTemp: Error parsing weather forecast temperatures from '{raw_temps_str}': {e}")
                future_temps_csv = ""
        else:
            _LOGGER.warning(f"VirtualOutdoorTemp: Could not get weather forecast temperatures from {weather_entity_id}. Pre-boost may not work.")
            future_temps_csv = ""

        # --- Hämta framtida elpriser ---
        # Nu hämtar vi från sensor.nordpool_tibber attribut 'today', som har bekräftats vara en lista av priser.
        raw_prices_list = get_attr(self.hass, electricity_price_entity_id, "today") # <-- Denna returnerar en LISTA

        # Lägger till en debug-logg för att bekräfta typen direkt i koden
        _LOGGER.debug(f"VirtualOutdoorTemp: Raw electricity prices from attribute 'today': '{raw_prices_list}' (type: {type(raw_prices_list)})") 
        
        future_prices = []
        if raw_prices_list: # Om listan inte är tom eller None
            try:
                # Iterera direkt över listan och konvertera varje element till float
                # safe_float() hanterar redan konverteringen och None för ogiltiga värden
                future_prices = [safe_float(p) for p in raw_prices_list if safe_float(p) is not None] # <-- ÄNDRAD HÄR: Itererar direkt, ingen split()
                _LOGGER.debug(f"VirtualOutdoorTemp: Parsed future_prices: {future_prices}")
            except Exception as e:
                _LOGGER.warning(f"VirtualOutdoorTemp: Error parsing electricity price forecast from attribute 'today' of '{electricity_price_entity_id}': {e}. Raw data: '{raw_prices_list}'")
                future_prices = []
        else:
            _LOGGER.warning(f"VirtualOutdoorTemp: Could not get electricity price forecast from attribute 'today' of {electricity_price_entity_id}. Pre-boost may not work.")
            future_prices = []

        # --- Hantering av sommarläge baserat på temperaturtröskel ---
        summer_mode_threshold_str = get_state(self.hass, summer_threshold_entity_id)
        summer_mode_threshold = safe_float(summer_mode_threshold_str)
        _LOGGER.debug(f"VirtualOutdoorTemp: Summer mode threshold raw: '{summer_mode_threshold_str}', parsed: {summer_mode_threshold}")

        # Om sommarlägeströskeln är tillgänglig OCH verklig utomhustemp är över eller lika med den
        if summer_mode_threshold is not None and real_outdoor_temp >= summer_mode_threshold:
            _LOGGER.info(f"VirtualOutdoorTemp: Summer mode activated. Real outdoor temp ({real_outdoor_temp}°C) >= threshold ({summer_mode_threshold}°C). Setting virtual temp to 25.0 °C.")
            self._state = 25.0
            
            # Uppdatera common_attributes med det korrekta tröskelvärdet
            common_attributes = {
                "Innetemp": round(indoor_temp, 2),
                "Måltemp": round(target_temp, 2),
                "Elpris": round(current_electricity_price, 2) if current_electricity_price is not None else None,
                "Ute (verklig)": round(real_outdoor_temp, 2),
                "Sommartröskel": round(summer_mode_threshold, 2), # Visar tröskelvärdet
                "Tröghet": round(current_inertia, 2),
                "Delta till mål": round(diff, 2),
                "Aggressivitet": round(aggressiveness, 2),
            }
            self._attributes.update(common_attributes)
            self._attributes.update({
                "scaling_factor": 0,
                "Läge": "summer_mode",
                "Virtuell UteTemp": self._state
            })
            return # Avsluta uppdateringen, vi är i sommarläge

        # Om sommarläget INTE är aktivt, fortsätt med de vanliga beräkningarna
        # Spara alla dessa attribut nu, uppdateras sedan i varje läge
        common_attributes = {
            "Innetemp": round(indoor_temp, 2),
            "Måltemp": round(target_temp, 2),
            "Elpris": round(current_electricity_price, 2) if current_electricity_price is not None else None,
            "Ute (verklig)": round(real_outdoor_temp, 2),
            "Sommartröskel": round(summer_mode_threshold, 2) if summer_mode_threshold is not None else None, # Visar tröskelvärdet även om inte aktivt
            "Tröghet": round(current_inertia, 2),
            "Delta till mål": round(diff, 2),
            "Aggressivitet": round(aggressiveness, 2),
        }

        # Original pre-boost logik
        should_preboost = check_combined_preboost(future_temps_csv, future_prices, lookahead_hours=6)
        if should_preboost:
            _LOGGER.info("VirtualOutdoorTemp: Pre-boost activated!")
            pre_boost_temp_offset = -5.0
            fake_temp = real_outdoor_temp + pre_boost_temp_offset
            
            preboost_max_temp = 20.0
            fake_temp = min(fake_temp, preboost_max_temp) 

            self._state = round(fake_temp, 1)
            self._attributes.update(common_attributes)
            self._attributes.update({
                "scaling_factor": 0,
                "Läge": "pre_boost",
                "Virtuell UteTemp": self._state
            })
            _LOGGER.info("VirtualOutdoorTemp: Pre-boost output (fake temp: %.1f °C)", fake_temp)
            return

        # Original neutral/balance logik
        if abs(diff) <= 0.5:
            self._state = min(real_outdoor_temp, 20.0)
            self._attributes.update(common_attributes)
            self._attributes.update({
                "scaling_factor": 0,
                "Läge": "neutral",
                "Virtuell UteTemp": self._state
            })
            _LOGGER.info("VirtualOutdoorTemp: Neutral (within tolerance)")
        else:
            # Säkerställ att aggressiveness är inom rimliga gränser
            aggressiveness = max(1.0, min(5.0, aggressiveness))
            
            # Beräkna scaling_factor med hänsyn till tröghet och aggressivitet
            scaling_factor = aggressiveness * (1 / current_inertia)
            
            # Begränsa scaling_factor
            scaling_factor = max(0.1, min(5.0, scaling_factor))

            # KORREKT LOGIK FÖR FAKE_TEMP:
            # Om diff är positiv (innetemp > måltemp, dvs. FÖR VARMT):
            # Vi vill signalera en HÖGRE virtuell utetemperatur för att värmepumpen ska dra ner.
            # fake_temp = real_outdoor_temp + (diff * scaling_factor)
            #
            # Om diff är negativ (innetemp < måltemp, dvs. FÖR KALLT):
            # Vi vill signalera en LÄGRE virtuell utetemperatur för att värmepumpen ska öka.
            # fake_temp = real_outdoor_temp + (diff * scaling_factor) (eftersom diff är negativ)
            fake_temp = real_outdoor_temp + (diff * scaling_factor) # <-- Denna rad är nu korrekt!

            # Hantering av max/min gränser
            # max_virtual_temp_for_heating_modes = 20.0 (kommenteras bort, används inte direkt längre på samma sätt)
            if diff < 0: # För kallt inne (negativ diff), vill värma.
                 # Sätt en övre gräns för den "kalla" signalen så den inte överstiger 20.0 om den vill värma.
                 # En virtuell temp över 20.0 indikerar att ingen värme behövs.
                 fake_temp = min(fake_temp, 20.0)
                 _LOGGER.info("VirtualOutdoorTemp: Adjusted output (fake temp: %.1f °C, diff: %.2f) - Heating", fake_temp, diff)
            else: # diff >= 0 (för varmt inne eller inom tolerans), vill bromsa eller är neutral.
                # Ingen övre gräns här. När det är för varmt inne ska fake_temp kunna gå högt
                # för att helt stänga av värmen.
                _LOGGER.info("VirtualOutdoorTemp: Adjusted output (fake temp: %.1f °C, diff: %.2f) - Braking/Neutral", fake_temp, diff)

            self._state = round(fake_temp, 1)
            self._attributes.update(common_attributes)
            self._attributes.update({
                "scaling_factor": round(scaling_factor, 2),
                "Läge": "balance",
                "Virtuell UteTemp": self._state
            })
