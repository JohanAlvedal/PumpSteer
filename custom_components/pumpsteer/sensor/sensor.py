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

from ..control import PIController
from ..electricity_price import async_hybrid_classify_with_history, classify_prices
from ..settings import (
    DEFAULT_HOUSE_INERTIA,
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
    """Safely get current price and category for a given time slot."""
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
    """PumpSteer sensor for heat pump control."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the PumpSteer sensor."""
        self.hass = hass
        if not hasattr(self.hass, "data"):
            self.hass.data = {}
        self._config_entry = config_entry
        self._state = None
        self._attributes = {}
        self._name = "PumpSteer"
        self._last_update_time = None
        self._pi_controller = PIController()
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
        """Called when the entity is added to Home Assistant."""
        if self.ml_collector and hasattr(self.ml_collector, "async_load_data"):
            await self.ml_collector.async_load_data()
            _LOGGER.debug("ML data loaded successfully")

        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal from Home Assistant."""
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
        """Handle options update event."""
        self._config_entry = entry
        await self.async_update()

    def _get_sensor_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch sensor data from Home Assistant."""
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
        """Validate that required runtime data is available."""
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
        """Calculate output temperature based on current conditions."""
        indoor_temp = sensor_data["indoor_temp"]
        outdoor_temp = sensor_data["outdoor_temp"]
        target_temp = sensor_data["target_temp"]
        summer_threshold = sensor_data["summer_threshold"]
        aggressiveness = sensor_data["aggressiveness"]
        outdoor_temp_forecast_entity = sensor_data["outdoor_temp_forecast_entity"]

        temp_forecast_csv = None

        if outdoor_temp_forecast_entity:
            temp_forecast_csv = get_state(self.hass, outdoor_temp_forecast_entity)

        forecast_bias = self._calculate_forecast_feedforward(
            temp_forecast_csv=temp_forecast_csv,
            outdoor_temp=outdoor_temp,
            summer_threshold=summer_threshold,
        )

        if temp_forecast_csv and should_precool(
            temp_forecast_csv, summer_threshold + PRECOOL_MARGIN
        ):
            self._reset_pi_state(update_time)
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
                base_fake_temp=outdoor_temp,
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
                    "control_target_temperature": target_temp,
                    "display_target_temperature": target_temp,
                    "control_error_c": 0.0,
                    "pid_output": 0.0,
                    "pid_error": 0.0,
                    "pid_integral": self._pi_controller.integral,
                    "pid_derivative": 0.0,
                    "pi_output": 0.0,
                    "pi_output_raw": 0.0,
                    "pi_error": 0.0,
                    "pi_integral": self._pi_controller.integral,
                    "pi_derivative": 0.0,
                    "heating_demand_c": 0.0,
                    "heating_demand_raw_c": 0.0,
                    "price_feedforward_c": 0.0,
                    "forecast_feedforward_c": forecast_bias,
                    "feedforward_total_c": forecast_bias,
                    "pi_feedforward": forecast_bias,
                    "brake_delta_c": fake_temp - outdoor_temp,
                    "final_fake_temp_c": fake_temp,
                },
            )

        if outdoor_temp >= summer_threshold:
            self._reset_pi_state(update_time)
            return outdoor_temp, "summer_mode", {
                "brake_mode": "summer_mode",
                "brake_factor": 0.0,
                "brake_requested": False,
                "brake_reason": "none",
                "control_target_temperature": target_temp,
                "display_target_temperature": target_temp,
                "control_error_c": 0.0,
                "pid_output": 0.0,
                "pid_error": 0.0,
                "pid_integral": self._pi_controller.integral,
                "pid_derivative": 0.0,
                "pi_output": 0.0,
                "pi_output_raw": 0.0,
                "pi_error": 0.0,
                "pi_integral": self._pi_controller.integral,
                "pi_derivative": 0.0,
                "heating_demand_c": 0.0,
                "heating_demand_raw_c": 0.0,
                "price_feedforward_c": 0.0,
                "forecast_feedforward_c": forecast_bias,
                "feedforward_total_c": forecast_bias,
                "pi_feedforward": forecast_bias,
                "brake_delta_c": 0.0,
                "final_fake_temp_c": outdoor_temp,
            }

        target_temp_for_logic = target_temp
        price_feedforward_gain = self._get_runtime_value(
            config, "pi_price_feedforward_gain", 1.0, 0.0, 10.0
        )
        if "very_cheap" in price_category and price_feedforward_gain <= 0.0:
            target_temp_for_logic += CHEAP_PRICE_OVERSHOOT

        brake_temp = (
            outdoor_temp + WINTER_BRAKE_TEMP_OFFSET
            if outdoor_temp < WINTER_BRAKE_THRESHOLD
            else BRAKE_FAKE_TEMP
        )

        price_is_high = (
            "expensive" in price_category
            or "very_expensive" in price_category
            or "extreme" in price_category
        )

        normalized_aggressiveness = min(1.0, max(0.0, aggressiveness / 5.0))
        accepted_comfort_drop = normalized_aggressiveness * 1.0
        comfort_floor = target_temp_for_logic - accepted_comfort_drop
        allow_price_brake = (
            aggressiveness > 0.0 and price_is_high and indoor_temp > comfort_floor
        )
        brake_requested = allow_price_brake
        brake_reason = "price" if allow_price_brake else "none"
        pi_should_freeze = brake_requested or self._brake_factor > 0.0

        (
            heating_demand_c,
            heating_demand_raw_c,
            pi_error,
            pi_derivative,
            feedforward_total_c,
            price_feedforward_c,
            forecast_feedforward_c,
        ) = self._calculate_pi_output(
            target_temp=target_temp_for_logic,
            indoor_temp=indoor_temp,
            outdoor_temp=outdoor_temp,
            aggressiveness=aggressiveness,
            update_time=update_time,
            braking_active=pi_should_freeze,
            price_category=price_category,
            forecast_bias=forecast_bias,
            config=config,
        )

        # Higher heating demand should lower the fake outdoor temperature.
        pi_fake_temp = min(
            max(outdoor_temp - heating_demand_c, MIN_FAKE_TEMP),
            MAX_FAKE_TEMP,
        )

        fake_temp, mode, brake_factor = self._apply_brake_ramp(
            base_fake_temp=pi_fake_temp,
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
                "control_target_temp": target_temp_for_logic,
                "display_target_temp": target_temp,
                "control_target_temperature": target_temp_for_logic,
                "display_target_temperature": target_temp,
                "control_error_c": pi_error,
                "comfort_floor_c": comfort_floor,
                # Keep PID keys for backward compatibility.
                # Negative output still means more heating for old dashboards.
                "pid_output": -heating_demand_c,
                "pid_error": pi_error,
                "pid_integral": self._pi_controller.integral,
                "pid_derivative": pi_derivative,
                "pi_output": -heating_demand_c,
                "pi_output_raw": -heating_demand_raw_c,
                "pi_error": pi_error,
                "pi_integral": self._pi_controller.integral,
                "pi_derivative": pi_derivative,
                "heating_demand_c": heating_demand_c,
                "heating_demand_raw_c": heating_demand_raw_c,
                "price_feedforward_c": price_feedforward_c,
                "forecast_feedforward_c": forecast_feedforward_c,
                "feedforward_total_c": feedforward_total_c,
                "pi_feedforward": feedforward_total_c,
                "brake_delta_c": fake_temp - pi_fake_temp,
                "final_fake_temp_c": fake_temp,
            },
        )

    def _get_runtime_value(
        self,
        config: Dict[str, Any],
        key: str,
        default: float,
        min_v: float,
        max_v: float,
    ) -> float:
        """Get a clamped numeric runtime value from config."""
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
        price_category: str,
        forecast_bias: float,
        config: Dict[str, Any],
    ) -> Tuple[float, float, float, float, float, float, float]:
        """Calculate heating demand from PI and external feedforward."""
        kp = self._get_runtime_value(config, "pid_kp", PID_KP, 0.0, 20.0)
        ki = self._get_runtime_value(config, "pid_ki", PID_KI, 0.0, 2.0)
        kd = self._get_runtime_value(config, "pid_kd", PID_KD, 0.0, 2.0)
        integral_clamp = self._get_runtime_value(
            config, "pid_integral_clamp", PID_INTEGRAL_CLAMP, 0.0, 30.0
        )
        output_clamp = self._get_runtime_value(
            config, "pid_output_clamp", PID_OUTPUT_CLAMP, 0.0, 30.0
        )
        price_feedforward_gain = self._get_runtime_value(
            config, "pi_price_feedforward_gain", 1.0, 0.0, 10.0
        )
        forecast_feedforward_gain = self._get_runtime_value(
            config, "pi_forecast_feedforward_gain", 1.0, 0.0, 10.0
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

        price_bias = self._price_feedforward_from_category(price_category)
        feedforward_bias = (price_bias * price_feedforward_gain) + (
            forecast_bias * forecast_feedforward_gain
        )

        if indoor_temp < target_temp and feedforward_bias > 0.0:
            # Comfort has priority: do not let positive feedforward reduce heating
            # demand while the house is colder than target.
            feedforward_bias = 0.0

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
            # Keep PI pure. Feedforward is applied outside the controller.
            feedforward_bias=0.0,
            integral_clamp=integral_clamp,
            output_clamp=output_clamp,
            min_fake_temp=MIN_FAKE_TEMP,
            max_fake_temp=MAX_FAKE_TEMP,
            brake_behavior=brake_behavior,
            decay_per_minute_on_brake=decay_per_minute,
        )

        # Convert legacy PI offset sign convention into positive heating demand.
        # Old behavior:
        #   negative offset => more heating
        # New interpretation:
        #   positive heating demand => more heating
        pi_heating_demand_raw = -result.offset

        heating_demand = pi_heating_demand_raw + feedforward_bias

        # Clamp final heating demand so fake outdoor temperature remains valid.
        dynamic_min_heating_demand = outdoor_temp - MAX_FAKE_TEMP
        dynamic_max_heating_demand = outdoor_temp - MIN_FAKE_TEMP
        heating_demand = min(
            max(heating_demand, dynamic_min_heating_demand),
            dynamic_max_heating_demand,
        )

        return (
            heating_demand,
            pi_heating_demand_raw,
            result.error,
            result.derivative,
            feedforward_bias,
            price_bias * price_feedforward_gain,
            forecast_bias * forecast_feedforward_gain,
        )

    def _reset_pi_state(self, update_time: datetime) -> None:
        """Reset PI controller state."""
        self._pi_controller.reset(update_time)

    def _price_feedforward_from_category(self, price_category: str) -> float:
        """Map price category to a feedforward temperature bias."""
        lowered = (price_category or "").lower()
        if "extreme" in lowered:
            return 1.8
        if "very_expensive" in lowered:
            return 1.2
        if "expensive" in lowered:
            return 0.6
        if "very_cheap" in lowered:
            return -1.0
        if "cheap" in lowered:
            return -0.4
        return 0.0

    def _calculate_forecast_feedforward(
        self,
        temp_forecast_csv: Optional[str],
        outdoor_temp: float,
        summer_threshold: float,
    ) -> float:
        """Calculate forecast-driven feedforward from trend and warm bias."""
        if not temp_forecast_csv:
            return 0.0

        values = []
        for token in temp_forecast_csv.split(","):
            parsed = safe_float(token)
            if parsed is None:
                continue
            values.append(parsed)

        if len(values) < 2:
            return 0.0

        horizon = values[: min(6, len(values))]
        trend = horizon[-1] - horizon[0]
        warm_bias = (sum(horizon) / len(horizon)) - summer_threshold
        outdoor_pull = (sum(horizon) / len(horizon)) - outdoor_temp
        raw = (0.20 * trend) + (0.15 * warm_bias) + (0.10 * outdoor_pull)
        return min(max(raw, -2.0), 2.0)

    def _apply_brake_ramp(
        self,
        base_fake_temp: float,
        brake_requested: bool,
        brake_target_temp: float,
        update_time: datetime,
        config: Dict[str, Any],
    ) -> Tuple[float, str, float]:
        """Apply bounded brake modifier with smooth ramp in and out."""
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
        max_brake_delta = self._get_runtime_value(
            config, "brake_max_modifier_c", 1.5, 0.0, 10.0
        )

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

        brake_delta = (brake_target_temp - base_fake_temp) * effective_strength
        brake_delta = min(max(brake_delta, -max_brake_delta), max_brake_delta)
        fake_temp = base_fake_temp + brake_delta
        fake_temp = min(max(fake_temp, MIN_FAKE_TEMP), MAX_FAKE_TEMP)
        return fake_temp, mode, self._brake_factor

    def _collect_ml_data(
        self,
        sensor_data: Dict[str, Any],
        mode: str,
        fake_temp: float,
        control_debug: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Collect data for machine learning."""
        if not self.ml_collector:
            return

        control_debug = control_debug or {}
        pi_error = safe_float(control_debug.get("pi_error")) or 0.0
        heating_active = (
            mode in {"pid", "brake_ramp_out"}
            and pi_error > 0.05
            and fake_temp < (sensor_data.get("outdoor_temp") or fake_temp)
        )

        ml_data = {
            "indoor_temp": sensor_data.get("indoor_temp"),
            "outdoor_temp": sensor_data.get("outdoor_temp"),
            "target_temp": sensor_data.get("target_temp"),
            "price_now": self._last_current_price,
            "aggressiveness": sensor_data.get("aggressiveness", 0),
            "inertia": sensor_data.get("inertia"),
            "mode": mode,
            "fake_outdoor_temp": fake_temp,
            "heating_active": heating_active,
            "heat_demand": control_debug.get("heating_demand_c") if control_debug else None,
            "house_inertia": sensor_data.get("inertia"),
            "price_category": self._last_price_category,
            "timestamp": dt_util.now().isoformat(),
        }

        if not self._ml_session_started:
            self.ml_collector.start_session(ml_data)
            self._ml_session_started = True
            self._ml_session_start_mode = mode

        self.ml_collector.update_session(ml_data)

        session_should_end = mode in {"summer_mode", "precool"}
        session_should_end = session_should_end or (
            mode in {"full_brake", "brake_ramp_in"} and not heating_active
        )
        if self._ml_session_start_mode != mode and session_should_end:
            self.ml_collector.end_session("mode_change", ml_data)
            self._ml_session_started = False

    async def _get_price_data(
        self, config: Dict[str, Any], current_time: datetime
    ) -> Tuple[List[float], float, str, List[str], int, int, int]:
        """Fetch price data and classify prices."""
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
        holiday_or_categories: Any,
        categories_or_now_hour: Any,
        now_hour: Any,
        price_interval_minutes: int,
        current_slot_index: int,
        peak_filter_minutes: int = 30,
        price_categories_filtered_count: int = 0,
        control_debug: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build attribute dictionary for the sensor."""
        if isinstance(holiday_or_categories, bool):
            categories = (
                categories_or_now_hour
                if isinstance(categories_or_now_hour, list)
                else []
            )
        else:
            categories = (
                holiday_or_categories if isinstance(holiday_or_categories, list) else []
            )
            now_hour = categories_or_now_hour

        if not isinstance(now_hour, int):
            now_hour = dt_util.now().hour

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
            "heating": "temperature",
            "pid": "pi control",
            "full_brake": "brake overlay",
            "brake_ramp_in": "brake overlay",
            "brake_ramp_out": "brake overlay",
            "summer_mode": "summer",
            "precool": "pre-cool (warm forecast)",
            "error": "error in calculation",
        }

        if (
            mode in {"heating", "pid", "brake_ramp_out"}
            and control_debug
            and control_debug.get("pi_error", 0.0) > 0.0
            and "very_cheap" in price_category
        ):
            decision_reason = f"{mode} - Triggered by very cheap price"
        elif mode == "heating" and "very_cheap" in price_category:
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
            "control_target_temperature": (
                control_debug.get("control_target_temperature")
                if control_debug
                else sensor_data["target_temp"]
            ),
            "display_target_temperature": (
                control_debug.get("display_target_temperature")
                if control_debug
                else sensor_data["target_temp"]
            ),
            "indoor_temperature": sensor_data["indoor_temp"],
            "outdoor_temperature": sensor_data["outdoor_temp"],
            "summer_threshold": sensor_data["summer_threshold"],
            "braking_threshold_percent": round(braking_threshold_ratio * 100, 1),
            "price_factor_percent": round(price_factor * 100, 1),
            "last_updated": dt_util.now().isoformat(),
            "temp_error_c": round(
                sensor_data["indoor_temp"]
                - (
                    control_debug.get("control_target_temperature")
                    if control_debug
                    else sensor_data["target_temp"]
                ),
                2,
            ),
            "control_error_c": round(
                (
                    control_debug.get("control_error_c")
                    if control_debug
                    else sensor_data["indoor_temp"] - sensor_data["target_temp"]
                ),
                2,
            ),
            "pi_output_raw": (
                round(control_debug.get("pi_output_raw"), 3)
                if control_debug and control_debug.get("pi_output_raw") is not None
                else None
            ),
            "heating_demand_c": (
                round(control_debug.get("heating_demand_c"), 3)
                if control_debug and control_debug.get("heating_demand_c") is not None
                else None
            ),
            "heating_demand_raw_c": (
                round(control_debug.get("heating_demand_raw_c"), 3)
                if control_debug and control_debug.get("heating_demand_raw_c") is not None
                else None
            ),
            "price_feedforward_c": (
                round(control_debug.get("price_feedforward_c"), 3)
                if control_debug and control_debug.get("price_feedforward_c") is not None
                else None
            ),
            "forecast_feedforward_c": (
                round(control_debug.get("forecast_feedforward_c"), 3)
                if control_debug and control_debug.get("forecast_feedforward_c") is not None
                else None
            ),
            "feedforward_total_c": (
                round(control_debug.get("feedforward_total_c"), 3)
                if control_debug and control_debug.get("feedforward_total_c") is not None
                else None
            ),
            "brake_requested": (
                control_debug.get("brake_requested") if control_debug else False
            ),
            "brake_reason": (
                control_debug.get("brake_reason") if control_debug else "none"
            ),
            "brake_factor": (
                round(control_debug.get("brake_factor"), 3)
                if control_debug and control_debug.get("brake_factor") is not None
                else 0.0
            ),
            "brake_delta_c": (
                round(control_debug.get("brake_delta_c"), 3)
                if control_debug and control_debug.get("brake_delta_c") is not None
                else 0.0
            ),
            "final_fake_temp_c": (
                round(control_debug.get("final_fake_temp_c"), 3)
                if control_debug and control_debug.get("final_fake_temp_c") is not None
                else self._state
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
        """Update sensor data."""
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
                    "status": f"Missing: {', '.join(missing)}",
                    "last_updated": update_time.isoformat(),
                    "current_hour": now_hour,
                }
                return

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
                False,
                categories,
                now_hour,
                price_interval_minutes,
                current_slot_index,
                30,
                filtered_count,
                control_debug,
            )

            if self.ml_collector:
                self._collect_ml_data(sensor_data, mode, fake_temp, control_debug)

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
    """Set up the PumpSteer sensor entity."""
    sensor = PumpSteerSensor(hass, config_entry)
    async_add_entities([sensor], update_before_add=True)
