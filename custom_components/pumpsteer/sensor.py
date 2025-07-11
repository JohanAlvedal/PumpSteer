import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceInfo

from .pre_boost import check_combined_preboost
from .holiday import is_holiday_mode_active, HOLIDAY_TARGET_TEMPERATURE
from .temp_control_logic import calculate_temperature_output
from .electricity_price import classify_prices
from .utils import (
    safe_float, get_state, get_attr,
    safe_get_price_data, safe_parse_temperature_forecast,
    validate_required_entities, safe_get_entity_state_with_description,
    safe_array_slice
)

_LOGGER = logging.getLogger(__name__)

PREBOOST_MAX_OUTDOOR_TEMP = 10.0
DOMAIN = "pumpsteer"

class PumpSteerSensor(Entity):
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry
        self._state = None
        self._attributes = {}
        self._name = "PumpSteer"

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

    async def async_options_update_listener(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._config_entry = entry
        await self.async_update()

    async def async_update(self) -> None:
        config = {**self._config_entry.data, **self._config_entry.options}

        indoor_temp = safe_float(get_state(self.hass, config.get("indoor_temp_entity")))
        outdoor_temp = safe_float(get_state(self.hass, config.get("real_outdoor_entity")))
        target_temp = safe_float(get_state(self.hass, config.get("target_temp_entity")))
        summer_threshold = safe_float(get_state(self.hass, config.get("summer_threshold_entity"))) or 18.0

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
        now_hour = datetime.now().hour
        if prices and now_hour < len(prices):
            price_category = classify_prices(prices)[now_hour]
        else:
            price_category = "okänd"

        max_price = max(prices) if prices else 1.0
        price_factor = current_price / max_price if max_price > 0 else 0

        missing = []
        if indoor_temp is None:
            missing.append("Indoor Temperature")
        if outdoor_temp is None:
            missing.append("Outdoor Temperature")
        if target_temp is None:
            missing.append("Target Temperature")
        if not prices:
            missing.append("Electricity Prices")

        if missing:
            self._state = STATE_UNAVAILABLE
            self._attributes["Status"] = f"Missing: {', '.join(missing)}"
            _LOGGER.warning(f"PumpSteer: Missing sensor data: {', '.join(missing)}")
            return

        aggressiveness = safe_float(get_state(self.hass, "input_number.pumpsteer_aggressiveness")) or 0.0
        inertia = safe_float(get_state(self.hass, "input_number.house_inertia")) or 1.0

        holiday = is_holiday_mode_active(
            self.hass,
            config.get("holiday_mode_boolean_entity"),
            config.get("holiday_start_datetime_entity"),
            config.get("holiday_end_datetime_entity")
        )

        if holiday:
            target_temp = HOLIDAY_TARGET_TEMPERATURE

        braking_threshold_ratio = 1.0 - (aggressiveness / 5.0) * 0.4

        if outdoor_temp >= summer_threshold:
            self._state = 25.0
            mode = "summer_mode"
        elif price_category in ["dyrt", "extremt_dyrt"]:
            self._state = 25.0
            mode = "braking_by_price"
            _LOGGER.info(f"PumpSteer: Blocking heat at hour {now_hour} due to {price_category} price (set fake temp to 25 °C)")
        else:
            diff = indoor_temp - target_temp
            if abs(diff) <= 0.5:
                self._state = round(outdoor_temp, 1)
                mode = "neutral"
            else:
                fake_temp, mode = calculate_temperature_output(
                    indoor_temp,
                    target_temp,
                    outdoor_temp,
                    aggressiveness
                )
                self._state = round(fake_temp, 1)

        self._attributes.update({
            "Mode": mode,
            "Fake Outdoor Temperature": self._state,
            "Price Category": price_category,
            "Status": "OK",
            "Current Price": current_price,
            "Max Price": max_price,
            "Aggressiveness": aggressiveness,
            "Inertia": inertia,
            "Target Temperature": target_temp,
            "Indoor Temperature": indoor_temp,
            "Outdoor Temperature": outdoor_temp,
            "Braking Threshold (%)": round(braking_threshold_ratio * 100, 1),
            "Price Factor (%)": round(price_factor * 100, 1),
            "Holiday Mode": holiday,
            "Last Updated": datetime.now().isoformat(),
            "Temp Error (°C)": round(indoor_temp - target_temp, 2),
            "To Summer Threshold (°C)": round(summer_threshold - outdoor_temp, 2),
            "Next 3 Hours Prices": prices[now_hour:now_hour+3] if len(prices) >= now_hour + 3 else prices[now_hour:],
            "Decision Reason": f"{mode} - Triggered by {'price' if mode == 'braking_by_price' else 'temp' if mode == 'heating' else 'neutral'}"
        })


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    async_add_entities([PumpSteerSensor(hass, config_entry)], update_before_add=True)
