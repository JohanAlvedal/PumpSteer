import logging
import math
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from ..holiday import is_holiday_mode_active
from ..control import PIController, OffsetSmoother
from ..temp_control_logic import calculate_temperature_output
from ..electricity_price import async_hybrid_classify_with_history, classify_prices
from ..settings import (
    DEFAULT_HOUSE_INERTIA,
    HOLIDAY_TEMP,
    BRAKE_FAKE_TEMP,
    AGGRESSIVENESS_SCALING_FACTOR,
    WINTER_BRAKE_TEMP_OFFSET,
    WINTER_BRAKE_THRESHOLD,
    CHEAP_PRICE_OVERSHOOT,
    PRECOOL_MARGIN,
    PID_KP,
    PID_KI,
    PID_KD,
    PID_INTEGRAL_CLAMP,
    PID_OUTPUT_CLAMP,
    PID_INTEGRATOR_ON_BRAKE,
    PID_DECAY_PER_MINUTE_ON_BRAKE,
    BRAKE_RAMP_IN_MINUTES,
    BRAKE_RAMP_OUT_MINUTES,
    MIN_BRAKE_STRENGTH,
    MAX_BRAKE_STRENGTH,
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
)
from ..utils import (
    safe_float,
    get_state,
    get_attr,
    get_version,
    should_precool,
    detect_price_interval_minutes,
    compute_price_slot_index,
    get_price_window_for_hours,
)

_LOGGER = logging.getLogger(__name__)


try:
    from ..ml_adaptive import PumpSteerMLCollector

    ML_AVAILABLE = True
    _LOGGER.info("ML features available")
except ImportError as e:
    ML_AVAILABLE = False
    _LOGGER.warning("ML features disabled: %s", e)

DOMAIN = "pumpsteer"

SW_VERSION = get_version()

# Hardcoded entities
HARDCODED_ENTITIES = {
    "target_temp_entity": "input_number.indoor_target_temperature",
    "summer_threshold_entity": "input_number.pumpsteer_summer_threshold",
    "holiday_mode_boolean_entity": "input_boolean.holiday_mode",
    "holiday_start_datetime_entity": "input_datetime.holiday_start",
    "holiday_end_datetime_entity": "input_datetime.holiday_end",
    "hourly_forecast_temperatures_entity": "input_text.hourly_forecast_temperatures",
    "aggressiveness_entity": "input_number.pumpsteer_aggressiveness",
    "house_inertia_entity": "input_number.house_inertia",
    "price_model_entity": "input_select.pumpsteer_price_model",
}

NEUTRAL_TEMP_THRESHOLD = 0.5
DEFAULT_SUMMER_THRESHOLD = 18.0
DEFAULT_AGGRESSIVENESS = 3.0


def safe_get_current_price_and_category(
    prices: List[float], categories: List[str], slot_index: int, mode: str = "unknown"
) -> Tuple[float, str]:
    """Safely get current price and category for a given time slot"""
    if not prices or slot_index >= len(prices) or slot_index < 0:
        _LOGGER.warning(
            "Invalid price data access: slot=%s, prices_len=%s",
            slot_index,
            len(prices) if prices else 0,
        )
        return 0.0, "unknown"

    current_price = prices[slot_index]

    if not categories or slot_index >= len(categories):
        _LOGGER.warning(
            "Invalid category data access: slot=%s, categories_len=%s",
            slot_index,
            len(categories) if categories else 0,
        )
        price_category = "unknown"
    else:
        price_category = f"{categories[slot_index]} ({mode})"

    return current_price, price_category


def filter_short_price_peaks(
    categories: List[str],
    interval_minutes: int,
    min_duration_minutes: int = 30,
    peak_levels: Tuple[str, ...] = ("expensive", "very_expensive", "extreme"),
) -> List[str]:
    """Replace short price peaks with a neighboring non-peak category."""
    if not categories or interval_minutes <= 0:
        return list(categories)

    min_slots = max(1, math.ceil(min_duration_minutes / interval_minutes))
    if min_slots <= 1:
        return list(categories)

    def is_peak(category: str) -> bool:
        return any(level in category for level in peak_levels)

    result = list(categories)
    index = 0
    total = len(categories)

    while index < total:
        if not is_peak(categories[index]):
            index += 1
            continue

        start = index
        while index < total and is_peak(categories[index]):
            index += 1
        end = index - 1
        run_len = end - start + 1

        if run_len < min_slots:
            replacement = None
            left_index = start - 1
            right_index = end + 1

            if left_index >= 0 and not is_peak(categories[left_index]):
                replacement = categories[left_index]
            elif right_index < total and not is_peak(categories[right_index]):
                replacement = categories[right_index]
            else:
                replacement = "normal"

            for replace_index in range(start, end + 1):
                result[replace_index] = replacement

    return result


class PumpSteerSensor(Entity):
    """PumpSteer sensor for heat pump control"""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the PumpSteer sensor"""
        self.hass = hass
        if not hasattr(self.hass, "data"):
            self.hass.data = {}
        self._config_entry = config_entry
        self._state = None
        self._attributes = {}
        self._name = "PumpSteer"
        self._last_update_time = None
        self._pi_controller = PIController()
        self._offset_smoother = OffsetSmoother()
        self._brake_factor = 0.0
        self._brake_last_update_time = None

        self._attr_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"
        self._attr_state_class = "measurement"
        self._attr_unique_id = config_entry.entry_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="Custom",
            model="Heat Pump Controller",
            sw_version=SW_VERSION,
        )

        self.ml_collector = None
        self._ml_session_started = False
        self._ml_session_start_mode = None
        self._last_price_category = "unknown"
        self._last_current_price = None
        self._owns_ml_collector = False

        if ML_AVAILABLE:
            domain_data = hass.data.setdefault(DOMAIN, {})
            collectors = domain_data.setdefault("ml_collectors", {})
            self.ml_collector = collectors.get(config_entry.entry_id)
            if self.ml_collector is None:
                self.ml_collector = PumpSteerMLCollector(hass)
                collectors[config_entry.entry_id] = self.ml_collector
                self._owns_ml_collector = True
            else:
                self._owns_ml_collector = False
            _LOGGER.info("PumpSteer: ML system enabled")

        else:
            _LOGGER.info("PumpSteer: Running without ML features")

        config_entry.add_update_listener(self.async_options_update_listener)
        _LOGGER.debug("PumpSteerSensor: Initialization complete")

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
        return {**self._attributes, "friendly_name": "PumpSteer"}

    @property
    def unit_of_measurement(self) -> str:
        return self._attr_unit_of_measurement

    @property
    def device_class(self) -> str:
        return self._attr_device_class

    @property
    def icon(self) -> str:
        return "mdi:thermostat-box"

    @property
    def available(self) -> bool:
        return self._state != STATE_UNAVAILABLE

    @property
    def should_poll(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        """Called when the entity is added to Home Assistant"""
        if self.ml_collector and hasattr(self.ml_collector, "async_load_data"):
            await self.ml_collector.async_load_data()
            _LOGGER.debug("ML data loaded successfully")

        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal from Home Assistant"""
        if (
            self._owns_ml_collector
            and self.ml_collector
            and hasattr(self.ml_collector, "async_shutdown")
        ):
            await self.ml_collector.async_shutdown()
            collectors = self.hass.data.get(DOMAIN, {}).get("ml_collectors", {})
            collectors.pop(self._config_entry.entry_id, None)
        self.ml_collector = None
        await super().async_will_remove_from_hass()

    async def async_options_update_listener(self, entry: ConfigEntry) -> None:
        """Handle options update event"""
        self._config_entry = entry
        await self.async_update()

    def _get_sensor_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch sensor data from Home Assistant"""
        return {
            "indoor_temp": safe_float(
                get_state(self.hass, config.get("indoor_temp_entity"))
            ),
            "outdoor_temp": safe_float(
                get_state(self.hass, config.get("real_outdoor_entity"))
            ),
            "target_temp": safe_float(
                get_state(self.hass, HARDCODED_ENTITIES["target_temp_entity"])
            ),
            "summer_threshold": safe_float(
                get_state(self.hass, HARDCODED_ENTITIES["summer_threshold_entity"])
            )
            or DEFAULT_SUMMER_THRESHOLD,
            "aggressiveness": safe_float(
                get_state(self.hass, HARDCODED_ENTITIES["aggressiveness_entity"])
            )
            or DEFAULT_AGGRESSIVENESS,
            "inertia": safe_float(
                get_state(self.hass, HARDCODED_ENTITIES["house_inertia_entity"])
            )
            or DEFAULT_HOUSE_INERTIA,
            "outdoor_temp_forecast_entity": HARDCODED_ENTITIES[
                "hourly_forecast_temperatures_entity"
            ],
        }

    def _validate_required_data(
        self, sensor_data: Dict[str, Any], prices: List[float]
    ) -> Optional[List[str]]:
        missing = []

        if sensor_data["indoor_temp"] is None:
            missing.append("Indoor temperature")
        if sensor_data["outdoor_temp"] is None:
            missing.append("Outdoor temperature")
        if sensor_data["target_temp"] is None:
            missing.append("Target temperature")
        if not prices:
            missing.append("Electricity prices")

        return missing if missing else None

    def _calculate_output_temperature(
        self,
        sensor_data: Dict[str, Any],
        price_category: str,
        current_slot_index: int,
        update_time: datetime,
        config: Dict[str, Any],
    ) -> Tuple[float, str, Dict[str, Any]]:
        """Calculate output temperature based on current conditions"""
        indoor_temp = sensor_data["indoor_temp"]
        outdoor_temp = sensor_data["outdoor_temp"]
        target_temp = sensor_data["target_temp"]
        summer_threshold = sensor_data["summer_threshold"]
        aggressiveness = sensor_data["aggressiveness"]
        outdoor_temp_forecast_entity = sensor_data["outdoor_temp_forecast_entity"]

        temp_forecast_csv = None

        # Fetch forecast if entity provided
        if outdoor_temp_forecast_entity:
            temp_forecast_csv = get_state(self.hass, outdoor_temp_forecast_entity)

        if temp_forecast_csv and should_precool(
            temp_forecast_csv, summer_threshold + PRECOOL_MARGIN
        ):
            self._reset_pid_state(update_time)
            brake_temp = min(
                max(
                    outdoor_temp + WINTER_BRAKE_TEMP_OFFSET
                    if outdoor_temp < WINTER_BRAKE_THRESHOLD
                    else BRAKE_FAKE_TEMP,
                    MIN_FAKE_TEMP,
                ),
                MAX_FAKE_TEMP,
            )
            fake_temp, brake_mode, brake_factor = self._apply_brake_ramp(
                outdoor_temp=outdoor_temp,
                brake_requested=True,
                brake_target_temp=brake_temp,
                update_time=update_time,
                config=config,
            )
            return (
                fake_temp,
                "precool",
                {
                    "brake_mode": brake_mode,
                    "brake_factor": brake_factor,
                    "brake_requested": True,
                    "brake_reason": "precool",
                    "pid_output": 0.0,
                    "pid_error": 0.0,
                    "pid_integral": self._pi_controller.integral,
                    "pid_derivative": 0.0,
                    "pi_output": 0.0,
                    "pi_error": 0.0,
                    "pi_integral": self._pi_controller.integral,
                    "pi_derivative": 0.0,
                    "pi_feedforward": 0.0,
                },
            )

        if outdoor_temp >= summer_threshold:
            self._reset_pid_state(update_time)
            return outdoor_temp, "summer_mode", {
                "brake_mode": "summer_mode",
                "brake_factor": 0.0,
                "brake_requested": False,
                "brake_reason": "none",
                "pid_output": 0.0,
                "pid_error": 0.0,
                "pid_integral": self._pi_controller.integral,
                "pid_derivative": 0.0,
                "pi_output": 0.0,
                "pi_error": 0.0,
                "pi_integral": self._pi_controller.integral,
                "pi_derivative": 0.0,
                "pi_feedforward": 0.0,
            }

        # Allow slight overshoot only when prices are very cheap
        target_temp_for_logic = target_temp
        if "very_cheap" in price_category:
            target_temp_for_logic += CHEAP_PRICE_OVERSHOOT

        # Dynamic braking temperature based on outdoor temp
        brake_temp = (
            outdoor_temp + WINTER_BRAKE_TEMP_OFFSET
            if outdoor_temp < WINTER_BRAKE_THRESHOLD
            else BRAKE_FAKE_TEMP
        )

        temp_diff = indoor_temp - target_temp_for_logic
        temp_deficit = target_temp_for_logic - indoor_temp
        price_is_high = (
            "expensive" in price_category
            or "very_expensive" in price_category
            or "extreme" in price_category
        )

        normalized_aggressiveness = min(1.0, max(0.0, aggressiveness / 5.0))
        price_brake_window = (
            NEUTRAL_TEMP_THRESHOLD + 0.05 + (0.45 * normalized_aggressiveness)
        )
        allow_price_brake = price_is_high and temp_deficit <= price_brake_window

        temp_mode = "neutral"
        if abs(temp_diff) > NEUTRAL_TEMP_THRESHOLD:
            _, temp_mode = calculate_temperature_output(
                indoor_temp,
                target_temp_for_logic,
                outdoor_temp,
                aggressiveness,
                brake_temp,
            )

        brake_requested = temp_mode == "braking_by_temp" or allow_price_brake
        brake_reason = (
            "temperature"
            if temp_mode == "braking_by_temp"
            else "price"
            if allow_price_brake
            else "none"
        )

        pi_output, pi_error, pi_derivative, pi_feedforward = self._calculate_pi_output(
            target_temp=target_temp_for_logic,
            indoor_temp=indoor_temp,
            outdoor_temp=outdoor_temp,
            aggressiveness=aggressiveness,
            update_time=update_time,
            braking_active=brake_requested,
            config=config,
        )
        pi_fake_temp = min(max(outdoor_temp + pi_output, MIN_FAKE_TEMP), MAX_FAKE_TEMP)

        fake_temp, mode, brake_factor = self._apply_brake_ramp(
            outdoor_temp=pi_fake_temp,
            brake_requested=brake_requested,
            brake_target_temp=brake_temp,
            update_time=update_time,
            config=config,
        )

        return (
            fake_temp,
            mode,
            {
                "brake_mode": mode,
                "brake_factor": brake_factor,
                "brake_requested": brake_requested,
                "brake_reason": brake_reason,
                # Keep PID keys for backward compatibility.
                "pid_output": pi_output,
                "pid_error": pi_error,
                "pid_integral": self._pi_controller.integral,
                "pid_derivative": pi_derivative,
                "pi_output": pi_output,
                "pi_error": pi_error,
                "pi_integral": self._pi_controller.integral,
                "pi_derivative": pi_derivative,
                "pi_feedforward": pi_feedforward,
            },
        )

    def _get_runtime_value(
        self, config: Dict[str, Any], key: str, default: float, min_v: float, max_v: float
    ) -> float:
        raw = config.get(key, default)
        value = safe_float(raw)
        if value is None:
            return default
        return min(max(value, min_v), max_v)

    def _calculate_pi_output(
        self,
        target_temp: float,
        indoor_temp: float,
        outdoor_temp: float,
        aggressiveness: float,
        update_time: datetime,
        braking_active: bool,
        config: Dict[str, Any],
    ) -> Tuple[float, float, float, float]:
        """Calculate PI-based output as fake outdoor temperature offset."""
        kp = self._get_runtime_value(config, "pid_kp", PID_KP, 0.0, 20.0)
        ki = self._get_runtime_value(config, "pid_ki", PID_KI, 0.0, 2.0)
        kd = self._get_runtime_value(config, "pid_kd", PID_KD, 0.0, 2.0)
        integral_clamp = self._get_runtime_value(
            config, "pid_integral_clamp", PID_INTEGRAL_CLAMP, 0.0, 30.0
        )
        output_clamp = self._get_runtime_value(
            config, "pid_output_clamp", PID_OUTPUT_CLAMP, 0.0, 30.0
        )
        feedforward_gain = self._get_runtime_value(
            config, "pi_feedforward_gain", 0.0, -10.0, 10.0
        )
        smoothing_minutes = self._get_runtime_value(
            config, "pi_smoothing_minutes", 0.0, 0.0, 120.0
        )
        brake_behavior = config.get(
            "pid_integrator_on_brake", PID_INTEGRATOR_ON_BRAKE
        ).lower()
        if brake_behavior not in {"freeze", "decay", "reset"}:
            brake_behavior = PID_INTEGRATOR_ON_BRAKE

        decay_per_minute = self._get_runtime_value(
            config,
            "pid_decay_per_minute_on_brake",
            PID_DECAY_PER_MINUTE_ON_BRAKE,
            0.5,
            1.0,
        )

        result = self._pi_controller.compute(
            target_temp=target_temp,
            indoor_temp=indoor_temp,
            outdoor_temp=outdoor_temp,
            aggressiveness=aggressiveness,
            update_time=update_time,
            braking_active=braking_active,
            kp=kp,
            ki=ki,
            kd=kd,
            feedforward_gain=feedforward_gain,
            integral_clamp=integral_clamp,
            output_clamp=output_clamp,
            min_fake_temp=MIN_FAKE_TEMP,
            max_fake_temp=MAX_FAKE_TEMP,
            brake_behavior=brake_behavior,
            decay_per_minute_on_brake=decay_per_minute,
        )
        smoothed_offset = self._offset_smoother.apply(
            raw_offset=result.offset,
            update_time=update_time,
            smoothing_minutes=smoothing_minutes,
        )
        dynamic_min_offset = MIN_FAKE_TEMP - outdoor_temp
        dynamic_max_offset = MAX_FAKE_TEMP - outdoor_temp
        smoothed_offset = min(max(smoothed_offset, dynamic_min_offset), dynamic_max_offset)

        return smoothed_offset, result.error, result.derivative, result.feedforward

    def _reset_pid_state(self, update_time: datetime) -> None:
        """Reset PI controller and smoothing states."""
        self._pi_controller.reset(update_time)
        self._offset_smoother.reset(update_time, 0.0)

    def _apply_brake_ramp(
        self,
        outdoor_temp: float,
        brake_requested: bool,
        brake_target_temp: float,
        update_time: datetime,
        config: Dict[str, Any],
    ) -> Tuple[float, str, float]:
        """Apply smooth ramp in/out for brake effect and blend with base control."""
        ramp_in_minutes = self._get_runtime_value(
            config, "brake_ramp_in_minutes", BRAKE_RAMP_IN_MINUTES, 0.1, 120.0
        )
        ramp_out_minutes = self._get_runtime_value(
            config, "brake_ramp_out_minutes", BRAKE_RAMP_OUT_MINUTES, 0.1, 120.0
        )
        min_strength = self._get_runtime_value(
            config, "min_brake_strength", MIN_BRAKE_STRENGTH, 0.0, 1.0
        )
        max_strength = self._get_runtime_value(
            config, "max_brake_strength", MAX_BRAKE_STRENGTH, 0.0, 1.0
        )
        max_strength = max(max_strength, min_strength)

        if self._brake_last_update_time is None:
            dt_seconds = 60.0
        else:
            dt_seconds = max(
                (update_time - self._brake_last_update_time).total_seconds(),
                1.0,
            )

        up_rate = 1.0 / (ramp_in_minutes * 60.0)
        down_rate = 1.0 / (ramp_out_minutes * 60.0)

        if brake_requested:
            self._brake_factor += dt_seconds * up_rate
        else:
            self._brake_factor -= dt_seconds * down_rate

        self._brake_factor = min(max(self._brake_factor, 0.0), 1.0)
        self._brake_last_update_time = update_time

        if self._brake_factor <= 0.0:
            effective_strength = 0.0
            mode = "pid"
        else:
            effective_strength = min_strength + (
                (max_strength - min_strength) * self._brake_factor
            )
            if brake_requested and self._brake_factor < 1.0:
                mode = "brake_ramp_in"
            elif brake_requested:
                mode = "full_brake"
            else:
                mode = "brake_ramp_out"

        fake_temp = outdoor_temp + ((brake_target_temp - outdoor_temp) * effective_strength)
        fake_temp = min(max(fake_temp, MIN_FAKE_TEMP), MAX_FAKE_TEMP)
        return fake_temp, mode, self._brake_factor

    def _collect_ml_data(
        self, sensor_data: Dict[str, Any], mode: str, fake_temp: float
    ) -> None:
        """Collect data for machine learning"""
        if not self.ml_collector:
            return

        ml_data = {
            "indoor_temp": sensor_data.get("indoor_temp"),
            "outdoor_temp": sensor_data.get("outdoor_temp"),
            "target_temp": sensor_data.get("target_temp"),
            "price_now": self._last_current_price,
            "aggressiveness": sensor_data.get("aggressiveness", 0),
            "inertia": sensor_data.get("inertia"),
            "mode": mode,
            "fake_outdoor_temp": fake_temp,
            "heating_active": mode == "heating",
            "heat_demand": None,
            "house_inertia": sensor_data.get("inertia"),
            "price_category": self._last_price_category,
            "timestamp": dt_util.now().isoformat(),
        }

        if not self._ml_session_started:
            self.ml_collector.start_session(ml_data)
            self._ml_session_started = True
            self._ml_session_start_mode = mode

        self.ml_collector.update_session(ml_data)

        if self._ml_session_start_mode != mode and mode in [
            "neutral",
            "summer_mode",
        ]:
            self.ml_collector.end_session("mode_change", ml_data)
            self._ml_session_started = False

    async def _get_price_data(
        self, config: Dict[str, Any], current_time: datetime
    ) -> Tuple[List[float], float, str, List[str], int, int, int]:
        """Fetch price data and classify prices"""
        entity_id = config.get("electricity_price_entity")

        if not entity_id:
            _LOGGER.error("No electricity price entity configured")
            return [], 0.0, "unknown", [], 60, 0, 0

        prices_raw = get_attr(self.hass, entity_id, "today") or get_attr(
            self.hass, entity_id, "raw_today"
        )
        if not prices_raw:
            _LOGGER.warning("Could not retrieve electricity prices from %s", entity_id)
            return [], 0.0, "unknown", [], 60, 0, 0

        def extract_price_value(item: Any) -> Optional[float]:
            if item is None:
                return None

            if isinstance(item, dict):
                if "value" in item:
                    return extract_price_value(item.get("value"))
                if "price" in item:
                    return extract_price_value(item.get("price"))
                return None

            if isinstance(item, (float, int)):
                return float(item)

            if isinstance(item, str):
                stripped = item.strip()
                if not stripped or stripped.lower() in ("unknown", "unavailable"):
                    return None
                try:
                    return float(stripped)
                except ValueError:
                    return None

            return None

        prices = []
        for item in prices_raw:
            value = extract_price_value(item)
            if value is None or not math.isfinite(value):
                continue
            prices.append(value)

        if not prices:
            _LOGGER.warning("No valid prices found after conversion")
            return [], 0.0, "unknown", [], 60, 0, 0

        price_interval_minutes = detect_price_interval_minutes(prices)
        current_slot_index = compute_price_slot_index(
            current_time,
            price_interval_minutes,
            len(prices),
        )

        mode = (
            get_state(self.hass, HARDCODED_ENTITIES["price_model_entity"]) or "hybrid"
        )
        categories = []

        if mode == "percentiles":
            categories = classify_prices(prices)
        else:
            categories = await async_hybrid_classify_with_history(
                self.hass,
                price_list=prices,
                price_entity_id=entity_id,
                trailing_hours=72,
            )

        filtered_categories = filter_short_price_peaks(
            categories,
            price_interval_minutes,
        )
        filtered_count = sum(
            1
            for original, filtered in zip(categories, filtered_categories)
            if original != filtered
        )

        current_price, price_category = safe_get_current_price_and_category(
            prices, filtered_categories, current_slot_index, mode
        )

        return (
            prices,
            current_price,
            price_category,
            filtered_categories,
            price_interval_minutes,
            current_slot_index,
            filtered_count,
        )

    def _build_attributes(
        self,
        sensor_data: Dict[str, Any],
        prices: List[float],
        current_price: float,
        price_category: str,
        mode: str,
        holiday: bool,
        categories: List[str],
        now_hour: int,
        price_interval_minutes: int,
        current_slot_index: int,
        peak_filter_minutes: int = 30,
        price_categories_filtered_count: int = 0,
        control_debug: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build attribute dictionary for the sensor"""
        max_price = max(prices) if prices else 1.0
        min_price = min(prices) if prices else 0.0

        price_range = max_price - min_price
        if price_range > 0:
            price_factor = (current_price - min_price) / price_range
        else:
            price_factor = 0.0

        price_factor = max(0.0, min(price_factor, 1.0))
        braking_threshold_ratio = (
            1.0 - (sensor_data["aggressiveness"] / 5.0) * AGGRESSIVENESS_SCALING_FACTOR
        )

        decision_triggers = {
            "braking_by_price": "price",
            "braking_by_temp": "temperature",
            "heating": "temperature",
            "cooling": "temperature",
            "summer_mode": "summer",
            "neutral": "neutral",
            "precool": "pre-cool (warm forecast)",
            "error": "error in calculation",
        }
        # If heating is enabled while prices are very cheap, the trigger should reflect that
        if mode == "heating" and "very_cheap" in price_category:
            decision_reason = f"{mode} - Triggered by very cheap price"
        else:
            decision_reason = (
                f"{mode} - Triggered by {decision_triggers.get(mode, 'unknown')}"
            )
        next_3_hours_prices = get_price_window_for_hours(
            prices,
            current_slot_index,
            3,
            price_interval_minutes,
        )

        attributes = {
            "mode": mode,
            "fake_outdoor_temperature": self._state,
            "price_category": price_category,
            "status": "ok",
            "current_price": round(current_price, 3),
            "max_price": round(max_price, 3),
            "aggressiveness": sensor_data["aggressiveness"],
            "inertia": sensor_data["inertia"],
            "target_temperature": sensor_data["target_temp"],
            "indoor_temperature": sensor_data["indoor_temp"],
            "outdoor_temperature": sensor_data["outdoor_temp"],
            "summer_threshold": sensor_data["summer_threshold"],
            "braking_threshold_percent": round(braking_threshold_ratio * 100, 1),
            "price_factor_percent": round(price_factor * 100, 1),
            "holiday_mode": holiday,
            "last_updated": dt_util.now().isoformat(),
            "temp_error_c": round(
                sensor_data["indoor_temp"] - sensor_data["target_temp"], 2
            ),
            "to_summer_threshold_c": round(
                sensor_data["summer_threshold"] - sensor_data["outdoor_temp"], 2
            ),
            "next_3_hours_prices": next_3_hours_prices,
            "decision_reason": decision_reason,
            "current_hour": now_hour,
            "current_price_slot_index": current_slot_index,
            "price_interval_minutes": price_interval_minutes,
            "peak_filter_minutes": peak_filter_minutes,
            "price_categories_filtered_count": price_categories_filtered_count,
            "data_quality": {
                "prices_count": len(prices),
                "categories_count": len(categories),
                "forecast_available": bool(sensor_data["outdoor_temp_forecast_entity"]),
            },
        }
        if control_debug:
            attributes["control_debug"] = control_debug

        return attributes

    async def async_update(self) -> None:
        """Update sensor data"""
        try:
            update_time = dt_util.now()
            now_hour = update_time.hour

            config = {**self._config_entry.data, **self._config_entry.options}
            sensor_data = self._get_sensor_data(config)
            (
                prices,
                current_price,
                price_category,
                categories,
                price_interval_minutes,
                current_slot_index,
                filtered_count,
            ) = await self._get_price_data(config, update_time)
            self._last_current_price = current_price
            self._last_price_category = price_category

            missing = self._validate_required_data(sensor_data, prices)
            if missing:
                self._state = STATE_UNAVAILABLE
                self._attributes = {
                    "Status": f"Missing: {', '.join(missing)}",
                    "Last Updated": update_time.isoformat(),
                    "Current Hour": now_hour,
                }
                return

            holiday = is_holiday_mode_active(
                self.hass,
                HARDCODED_ENTITIES["holiday_mode_boolean_entity"],
                HARDCODED_ENTITIES["holiday_start_datetime_entity"],
                HARDCODED_ENTITIES["holiday_end_datetime_entity"],
            )

            if holiday:
                sensor_data["target_temp"] = HOLIDAY_TEMP

            fake_temp, mode, control_debug = self._calculate_output_temperature(
                sensor_data,
                price_category,
                current_slot_index,
                update_time,
                config,
            )
            self._state = round(fake_temp, 1)

            self._attributes = self._build_attributes(
                sensor_data,
                prices,
                current_price,
                price_category,
                mode,
                holiday,
                categories,
                now_hour,
                price_interval_minutes,
                current_slot_index,
                30,
                filtered_count,
                control_debug,
            )

            if self.ml_collector:
                self._collect_ml_data(sensor_data, mode, fake_temp)

            self._last_update_time = update_time
        except Exception as err:
            _LOGGER.exception("PumpSteer sensor update failed: %s", err)
            self._state = STATE_UNAVAILABLE
            self._attributes = {
                "status": "error",
                "last_error": str(err),
                "last_updated": dt_util.now().isoformat(),
            }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PumpSteer sensor entity"""
    sensor = PumpSteerSensor(hass, config_entry)
    async_add_entities([sensor], update_before_add=True)
