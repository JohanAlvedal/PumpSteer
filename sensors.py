from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging
from datetime import datetime
from .pre_boost import check_combined_preboost

_LOGGER = logging.getLogger(__name__)

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

    async def async_update(self):
        data = self._entry.options

        indoor_entity = data.get("indoor_temp_entity")
        outdoor_entity = data.get("real_outdoor_entity")
        electricity_price_entity = data.get("electricity_price_entity")
        weather_entity = data.get("weather_entity")
        target_entity = data.get("target_temp_entity")

        indoor = safe_float(get_state(self.hass, indoor_entity))
        forecast_temp = safe_float(get_attr(self.hass, weather_entity, "temperature"))
        real_outdoor_temp = safe_float(get_state(self.hass, outdoor_entity))
        price = safe_float(get_state(self.hass, electricity_price_entity))
        target = safe_float(get_state(self.hass, target_entity))

        summer_threshold = safe_float(get_state(self.hass, "input_number.pumpsteer_summer_temp_threshold"))
        summer_mode_entity = self.hass.states.get("input_boolean.pumpsteer_summer_mode")
        summer_mode_state = summer_mode_entity.state if summer_mode_entity else "unknown"

        self._attributes = {
            "indoor_temperature": indoor,
            "target_temperature": target,
            "electricity_price": price,
            "real_outdoor_temperature": real_outdoor_temp,
            "summer_mode": summer_mode_state,
            "summer_mode_threshold": summer_threshold
        }

        if real_outdoor_temp is not None and summer_threshold is not None:
            if real_outdoor_temp > summer_threshold and summer_mode_state != "on":
                await self.hass.services.async_call("input_boolean", "turn_on", {
                    "entity_id": "input_boolean.pumpsteer_summer_mode"
                })
            elif real_outdoor_temp <= summer_threshold and summer_mode_state != "off":
                await self.hass.services.async_call("input_boolean", "turn_off", {
                    "entity_id": "input_boolean.pumpsteer_summer_mode"
                })

        if summer_mode_state == "on":
            self._state = 20.0
            self._attributes["mode"] = "summer_mode"
            _LOGGER.info("VirtualOutdoorTemp: Summer mode active")
            return

        if None in (indoor, target, price, forecast_temp, real_outdoor_temp):
            self._state = "unavailable"
            _LOGGER.warning("VirtualOutdoorTemp: Waiting for all sensors to be ready.")
            return

        diff = target - indoor
        within_range = abs(diff) <= 0.5

        adjusted_diff = diff

        raw_temps = get_state(self.hass, "input_text.hourly_forecast_temperatures")
        if raw_temps and summer_mode_state != "on":
            should_preboost = check_combined_preboost(raw_temps, [price], min_peak_hits=2)
            if should_preboost:
                preboost_min_temp = 20.0
                fake_temp = max(real_outdoor_temp - 6, preboost_min_temp)
                self._state = round(fake_temp, 1)
                self._attributes["mode"] = "preboost"
                _LOGGER.info("VirtualOutdoorTemp: Preboost active (fake temp: %.1f °C)", fake_temp)
                return

        if within_range:
            self._state = real_outdoor_temp
            self._attributes["mode"] = "neutral"
            _LOGGER.info("VirtualOutdoorTemp: Neutral (within tolerance)")
            return

        aggressiveness_entity = self.hass.states.get("input_number.pumpsteer_aggressiveness")
        aggressiveness = float(aggressiveness_entity.state) if aggressiveness_entity and aggressiveness_entity.state not in ["unknown", "unavailable"] else 0
        inertia = safe_float(get_state(self.hass, "input_number.house_inertia")) or 1
        scaling_factor = (aggressiveness / 5) * 2 * (1 / inertia)
        fake_temp = real_outdoor_temp - adjusted_diff * scaling_factor

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
