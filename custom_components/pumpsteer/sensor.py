# Standardimporter
import logging
from datetime import datetime, timedelta

# Home Assistant-specifika importer
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

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
    sensors = [
        PumpSteerSensor(hass, entry),
        PumpSteerFutureStrategySensor(hass, entry),
    ]
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
        self._last_outdoor_temp = None
        self._inertia_value = DEFAULT_INERTIA_VALUE
        self._name = "PumpSteer"

        # Sätt standard Home Assistant egenskaper
        self._attr_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"
        self._attr_state_class = "measurement"
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
        # Kombinera befintliga attribut med nya, vänliga namn
        return {
            **self._attributes,
            "friendly_name": "PumpSteer – Control Output"
        }

    @property
    def unit_of_measurement(self):
        """Returnerar enheten för mätning."""
        return "°C"

    @property
    def device_class(self):
        """Returnerar enhetsklassen."""
        return "temperature"

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
        indoor_temp = safe_float(get_state(self.hass, config.get("indoor_temp_entity")))
        real_outdoor_temp = safe_float(get_state(self.hass, config.get("real_outdoor_entity")))
        electricity_prices = get_attr(self.hass, config.get("electricity_price_entity"), "today")
        hourly_temps_csv = get_state(self.hass, config.get("hourly_forecast_temperatures_entity"))
        target_temp = safe_float(get_state(self.hass, config.get("target_temp_entity")))
        summer_threshold_temp = safe_float(get_state(self.hass, config.get("summer_threshold_entity")))
        aggressiveness = safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or 0.0
        user_defined_inertia = safe_float(get_state(self.hass, "input_number.house_inertia"))
        inertia = user_defined_inertia if user_defined_inertia is not None else self._inertia_value

        critical_entities_data = {
            "Inne (verklig)": indoor_temp,
            "Ute (verklig)": real_outdoor_temp,
            "Måltemp": target_temp,
            "Sommartröskel": summer_threshold_temp,
            "Elpriser (prognos)": electricity_prices,
            "Temperaturprognos": hourly_temps_csv,
        }

        missing_data_info = [name for name, value in critical_entities_data.items() if value is None]

        if missing_data_info:
            _LOGGER.warning("PumpSteer: Väntar på data för: %s. Försöker igen om 10 sekunder.", ", ".join(missing_data_info))
            self._state = STATE_UNAVAILABLE
            self._attributes["Status"] = f"Väntar på data: {', '.join(missing_data_info)}"
            # Schemalägg en ny uppdatering efter 10 sekunder
            self.async_on_remove(
                async_call_later(self.hass, timedelta(seconds=10), self.async_schedule_update_ha_state)
            )
            return

        self._attributes["Status"] = "OK"
        
        # --- KONTROLLERA LÄGE OCH SÄTT UTVÄRDE ---
        
        # 1. Summer Mode - prioriteras högst
        if real_outdoor_temp >= summer_threshold_temp:
            self._state = round(25.0, 1)
            self._attributes["Läge"] = "summer_mode"
            self._attributes["Pre-boost Aktiv"] = False
            _LOGGER.info("PumpSteer: Summer Mode activated (Outdoor temp: %.1f >= %.1f)", real_outdoor_temp, summer_threshold_temp)
        else:
            # 2. Braking Mode (baserat på pris) - prioriteras framför pre-boost
            max_price_in_forecast = max(electricity_prices) if electricity_prices else 0.0
            current_price = electricity_prices[0] if electricity_prices and electricity_prices[0] is not None else 0.0

            price_factor = 0.0
            if max_price_in_forecast > 0:
                price_factor = current_price / max_price_in_forecast
            
            # Dynamisk tröskel baserat på aggressivitet
            # Aggressivitet 0 -> tröskel 1.0 (aldrig bromsa), 5 -> tröskel 0.6 (bromsa tidigt)
            braking_threshold_ratio = 1.0 - (aggressiveness / 5.0) * 0.4 
            
            if price_factor >= braking_threshold_ratio:
                self._state = round(25.0, 1) # Sätter den virtuella utetemperaturen till en hög nivå
                self._attributes["Läge"] = "braking_mode"
                self._attributes["Pre-boost Aktiv"] = True # Använd detta för att pausa inertia-beräkning
                _LOGGER.info("PumpSteer: Braking mode activated due to high price (Aggressiveness: %.1f, Price Factor: %.2f)", aggressiveness, price_factor)
            else:
                # 3. Pre-boost Mode (baserat på prognos)
                boost_mode = None
                if real_outdoor_temp <= PREBOOST_MAX_OUTDOOR_TEMP:
                    boost_mode = check_combined_preboost(
                        hourly_temps_csv,
                        electricity_prices,
                        lookahead_hours=6,
                        cold_threshold=2.0,
                        price_threshold_ratio=0.8,
                        min_peak_hits=1,
                        aggressiveness=aggressiveness, # Skickar med aggressivitet till pre_boost
                        inertia=inertia
                    )
                else:
                    _LOGGER.info(f"PumpSteer: Pre-boost avaktiverat eftersom utomhustemperaturen ({real_outdoor_temp}°C) är över maxtröskeln ({PREBOOST_MAX_OUTDOOR_TEMP}°C).")
            
                if boost_mode == "preboost":
                    self._state = -15.0 # Mycket låg virtuell utetemp för att gasa
                    self._attributes["Läge"] = "preboost"
                    self._attributes["Pre-boost Aktiv"] = True
                    _LOGGER.info("PumpSteer: Preboost (gasa) activated to build heat buffer.")
                else:
                    # 4. Normal drift (heating/neutral)
                    diff = indoor_temp - target_temp
                    
                    # Använd aggressivitet för att justera hur snabbt den ska värma/bromsa
                    scaling_factor = aggressiveness * 0.5 
                    fake_temp = real_outdoor_temp + (diff * scaling_factor)

                    if diff < 0:
                        # Huset är kallare än målet
                        fake_temp = min(fake_temp, 20.0)
                        self._attributes["Läge"] = "heating"
                    else:
                        # Huset är vid eller över målet
                        self._attributes["Läge"] = "neutral" if abs(diff) < 0.5 else "braking_by_temp"
                        
                    self._state = round(fake_temp, 1)
                    self._attributes["Pre-boost Aktiv"] = False
                    _LOGGER.debug("PumpSteer: Normal operation (fake temp: %.1f °C, diff: %.2f) - Mode: %s", fake_temp, diff, self._attributes["Läge"])

        # --- BERÄKNING AV INERTIA ---
        current_time = datetime.now()
        
        # Logiken för inertia-beräkning är oförändrad, men jag har sett över den
        # för att se till att den är korrekt. Den pausar när 'Pre-boost Aktiv' är True.
        if self._last_update_time and (current_time - self._last_update_time) >= INERTIA_UPDATE_INTERVAL:
            if not self._attributes.get("Pre-boost Aktiv"):
                if self._previous_indoor_temp is not None and self._last_outdoor_temp is not None:
                    delta_indoor = indoor_temp - self._previous_indoor_temp
                    delta_outdoor = real_outdoor_temp - self._last_outdoor_temp
                    if abs(delta_outdoor) > 0.001:
                        new_inertia_contribution = delta_indoor / delta_outdoor
                        new_inertia_contribution = max(-5.0, min(5.0, new_inertia_contribution))
                        
                        self._inertia_value = (self._inertia_value * INERTIA_WEIGHT_FACTOR + new_inertia_contribution) / INERTIA_DIVISOR
                        self._inertia_value = max(MIN_INERTIA_VALUE, min(MAX_INERTIA_VALUE, self._inertia_value))
                        
                        house_inertia_entity_id = "input_number.house_inertia"
                        if house_inertia_entity_id:
                            self.hass.async_create_task(
                                self.hass.services.async_call(
                                    "input_number", "set_value",
                                    {"entity_id": house_inertia_entity_id, "value": round(self._inertia_value, 2)},
                                    blocking=False,
                                )
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
                _LOGGER.debug("Inertia-beräkning pausad pga Pre-boost/Braking-läge. Ingen uppdatering.")
        elif not self._last_update_time:
            self._last_update_time = current_time
            self._previous_indoor_temp = indoor_temp
            self._last_outdoor_temp = real_outdoor_temp

        current_inertia = user_defined_inertia if user_defined_inertia is not None else self._inertia_value

        self._attributes.update({
            "Ute (verklig)": real_outdoor_temp,
            "Inne (mål)": target_temp,
            "Inne (verklig)": indoor_temp,
            "Inertia": round(current_inertia, 2),
            "Aggressivitet": aggressiveness,
            "Sommartröskel": summer_threshold_temp,
            "Elpriser (prognos)": electricity_prices,
            "Pre-boost Aktiv": self._attributes.get("Pre-boost Aktiv", False),
        })
        _LOGGER.debug(f"PumpSteer: Final state: {self._state}°C, Mode: {self._attributes['Läge']}")

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

        # --- BERÄKNING AV FRAMTIDA STRATEGI ---
        
        # 1. Pre-boost logik (kallt + dyrt)
        cold_threshold = 2.0
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
        
        # 2. Braking-logik (bara dyrt)
        braking_threshold_ratio = 1.0 - (aggressiveness / 5.0) * 0.4
        braking_price_threshold = max_price * braking_threshold_ratio
        
        expensive_hours_count = 0
        
        for i in range(lookahead_hours):
            if prices[i] >= braking_price_threshold:
                expensive_hours_count += 1

        # Uppdatera sensorns tillstånd och attribut
        self._state = cold_expensive_matches
        self._attributes = {
            "strategy_status": "ok",
            "preboost_expected_in_hours": round(lead_time),
            "first_preboost_hour": next_preboost_hour,
            "cold_and_expensive_hours_next_6h": cold_expensive_matches,
            "expensive_hours_next_6h": expensive_hours_count,
            "braking_price_threshold_percent": round(braking_threshold_ratio * 100),
            "preboost_price_threshold_percent": round(adjusted_price_threshold_ratio * 100),
            "inertia": round(inertia, 2),
            "lead_time_hours": round(lead_time, 2),
            "aggressiveness": aggressiveness,
        }
