import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from ..holiday import is_holiday_mode_active
from ..temp_control_logic import calculate_temperature_output
from ..electricity_price import async_hybrid_classify_with_history, classify_prices
from ..const import (
    DATA_VERSION,
    DOMAIN,
    DEFAULT_HOUSE_INERTIA,
    HOLIDAY_TEMP,
    BRAKE_FAKE_TEMP,
    AGGRESSIVENESS_SCALING_FACTOR,
    WINTER_BRAKE_TEMP_OFFSET,
    WINTER_BRAKE_THRESHOLD,
    CHEAP_PRICE_OVERSHOOT,
    PRECOOL_MARGIN,
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
    PRICE_BRAKE_MAX_DELTA_PER_STEP,
    COMFORT_PI_KP,
    COMFORT_PI_KI,
    COMFORT_DEADBAND,
    BRAKE_WEIGHT,
    GAS_WEIGHT,
    COMFORT_BACKOFF_WEIGHT,
    CONTROL_BIAS_TEMP_SCALE,
    MIN_BLOCK_DURATION_MIN,
    PRICE_BLOCK_THRESHOLD_DELTA,
    PRICE_BLOCK_THRESHOLD_PERCENTILE,
    PRICE_BRAKE_PRE_MINUTES,
    PRICE_BRAKE_POST_MINUTES,
    PRICE_BLOCK_AREA_SCALE,
    LOOKAHEAD_HOURS,
    HEATING_THRESHOLD,
)
from ..pi_controller import (
    apply_rate_limit,
    update_pi_output,
)
from ..price_brake import build_forward_price_series, compute_price_brake
from ..utils import (
    safe_float,
    get_state,
    get_attr,
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


def compute_block_status(
    update_time: datetime,
    blocks: List["PriceBlock"],
) -> Tuple[
    Optional[datetime],
    Optional[datetime],
    bool,
    str,
    int,
    List[Tuple["PriceBlock", datetime, datetime]],
]:
    """Compute block timing and status details."""
    if not blocks:
        return None, None, False, "none", 0, []

    block_windows: List[Tuple["PriceBlock", datetime, datetime]] = []
    for block in blocks:
        block_start = update_time + timedelta(minutes=block.start_offset_minutes)
        block_end = update_time + timedelta(minutes=block.end_offset_minutes)
        block_windows.append((block, block_start, block_end))

    now_utc = (
        dt_util.utcnow()
        if hasattr(dt_util, "utcnow")
        else dt_util.as_utc(dt_util.now())
    )
    active_index = 0
    for index, (_, block_start, block_end) in enumerate(block_windows, start=1):
        block_start_utc = dt_util.as_utc(block_start)
        block_end_utc = dt_util.as_utc(block_end)
        if block_start_utc <= now_utc < block_end_utc:
            active_index = index
            break

    in_price_block = active_index > 0
    block_state = "active" if in_price_block else "upcoming"

    upcoming = [
        window
        for window in block_windows
        if dt_util.as_utc(window[1]) > now_utc
    ]
    upcoming.sort(key=lambda window: window[1])
    next_window = upcoming[0] if upcoming else None
    next_block_start = next_window[1] if next_window else None
    next_block_end = next_window[2] if next_window else None

    return (
        next_block_start,
        next_block_end,
        in_price_block,
        block_state,
        active_index,
        block_windows,
    )


class PumpSteerSensor(SensorEntity):
    """PumpSteer sensor for heat pump control"""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the PumpSteer sensor"""
        self.hass = hass
        self._config_entry = config_entry
        self._attributes = {}
        self._last_update_time = None

        self._attr_name = "PumpSteer"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = config_entry.entry_id
        self._attr_icon = "mdi:thermostat-box"
        self._attr_available = True

        sw_version = hass.data.get(DOMAIN, {}).get(DATA_VERSION, "unknown")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="Custom",
            model="Heat Pump Controller",
            sw_version=sw_version,
        )

        self.ml_collector = None
        self._ml_session_started = False
        self._ml_session_start_mode = None
        self._last_price_category = "unknown"
        self._comfort_integral = 0.0
        self._last_price_brake_level = None
        self._last_debug_log = None
        domain_data = self.hass.data.setdefault(DOMAIN, {})
        diagnostics_store = domain_data.setdefault("diagnostics", {})
        self._diagnostics = diagnostics_store.setdefault(config_entry.entry_id, {})

        if ML_AVAILABLE:
            self.ml_collector = PumpSteerMLCollector(hass)
            _LOGGER.info("PumpSteer: ML system enabled")

        else:
            _LOGGER.info("PumpSteer: Running without ML features")

        _LOGGER.debug("PumpSteerSensor: Initialization complete")

    @property
    def extra_state_attributes(self) -> dict:
        return {**self._attributes}

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
        if self.ml_collector and hasattr(self.ml_collector, "async_shutdown"):
            await self.ml_collector.async_shutdown()
        self.ml_collector = None
        await super().async_will_remove_from_hass()

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

    def _get_combined_prices(self, entity_id: str) -> List[float]:
        """Return combined today+tomorrow prices when available."""
        prices_today = get_attr(self.hass, entity_id, "today") or get_attr(
            self.hass, entity_id, "raw_today"
        )
        prices_tomorrow = get_attr(self.hass, entity_id, "tomorrow") or get_attr(
            self.hass, entity_id, "raw_tomorrow"
        )
        combined_raw = (prices_today or []) + (prices_tomorrow or [])
        combined = [
            float(p)
            for p in combined_raw
            if isinstance(p, (float, int)) and p is not None
        ]
        return combined

    def _compute_controls(
        self,
        sensor_data: Dict[str, Any],
        combined_prices: List[float],
        current_slot_index: int,
        price_interval_minutes: int,
        config: Dict[str, Any],
        current_price: float,
        price_category: str,
        update_time: datetime,
    ) -> Dict[str, Any]:
        """Compute price brake and comfort push controls."""
        dt_minutes = price_interval_minutes if price_interval_minutes > 0 else 60
        dt_hours = dt_minutes / 60.0

        forward_prices = build_forward_price_series(
            combined_prices, current_slot_index, dt_minutes, max_hours=LOOKAHEAD_HOURS
        )
        threshold_percentile = config.get(
            "price_brake_threshold_percentile", PRICE_BLOCK_THRESHOLD_PERCENTILE
        )
        if threshold_percentile is not None and threshold_percentile <= 0:
            threshold_percentile = None
        price_brake = compute_price_brake(
            forward_prices=forward_prices,
            dt_minutes=dt_minutes,
            threshold_delta=config.get(
                "price_brake_threshold_delta", PRICE_BLOCK_THRESHOLD_DELTA
            ),
            threshold_percentile=threshold_percentile,
            min_block_duration_min=MIN_BLOCK_DURATION_MIN,
            pre_brake_minutes=PRICE_BRAKE_PRE_MINUTES,
            post_release_minutes=PRICE_BRAKE_POST_MINUTES,
            area_scale=PRICE_BLOCK_AREA_SCALE,
            now_offset_minutes=0.0,
        )
        next_block = price_brake.get("next_block")

        (
            block_start,
            block_end,
            in_price_block,
            block_state,
            active_block_index,
            block_windows,
        ) = compute_block_status(update_time, price_brake["blocks"])
        temp_delta = sensor_data["indoor_temp"] - sensor_data["target_temp"]
        too_cold_to_brake = temp_delta < HEATING_THRESHOLD
        desired_brake_level = price_brake["brake_level"]
        threshold = price_brake["threshold"]
        aggressiveness = sensor_data["aggressiveness"]
        brake_blocked_reason = "allowed"

        category_label = price_category.split(" ")[0]
        expensive_now = (
            category_label in ("very_expensive", "extreme")
            or (category_label == "expensive" and current_price > threshold)
        )
        if desired_brake_level <= 0.0 and expensive_now and not too_cold_to_brake:
            base_min = 0.30
            scale = min(1.0, max(0.0, (aggressiveness - 1) / 2))
            desired_brake_level = max(
                desired_brake_level, base_min + 0.20 * scale
            )
            brake_blocked_reason = "expensive_now"
        pre_window_active = False
        if next_block is not None:
            pre_start = next_block.start_offset_minutes - PRICE_BRAKE_PRE_MINUTES
            pre_window_active = pre_start <= 0 < next_block.start_offset_minutes
        if (
            desired_brake_level <= 0.0
            and not in_price_block
            and not expensive_now
            and not pre_window_active
        ):
            brake_blocked_reason = "no_price_block"
        if too_cold_to_brake:
            desired_brake_level = 0.0
            brake_blocked_reason = "too_cold"
        if (
            current_price == 3.28
            and threshold == 2.54
            and category_label == "expensive"
            and not in_price_block
            and sensor_data["indoor_temp"] < sensor_data["target_temp"]
        ):
            if desired_brake_level <= 0.0 or brake_blocked_reason == "no_price_block":
                _LOGGER.warning(
                    "Expensive-now verification failed: brake=%s reason=%s",
                    desired_brake_level,
                    brake_blocked_reason,
                )
            else:
                _LOGGER.debug(
                    "Expensive-now verification passed: brake=%s reason=%s",
                    desired_brake_level,
                    brake_blocked_reason,
                )

        price_output, rate_limited = apply_rate_limit(
            desired_brake_level,
            self._last_price_brake_level,
            PRICE_BRAKE_MAX_DELTA_PER_STEP,
        )
        self._last_price_brake_level = price_output
        if (
            brake_blocked_reason == "allowed"
            and rate_limited
            and price_output < desired_brake_level
        ):
            brake_blocked_reason = "rate_limited"

        temp_error = sensor_data["target_temp"] - sensor_data["indoor_temp"]
        if abs(temp_error) < COMFORT_DEADBAND:
            temp_error = 0.0

        comfort_output, self._comfort_integral, comfort_high, comfort_low = (
            update_pi_output(
                temp_error,
                self._comfort_integral,
                COMFORT_PI_KP,
                COMFORT_PI_KI,
                dt_hours,
                -1.0,
                1.0,
            )
        )

        return {
            "price_brake_level": price_output,
            "price_baseline": price_brake["baseline"],
            "price_threshold": price_brake["threshold"],
            "price_area": price_brake["area"],
            "price_amplitude": price_brake["amplitude"],
            "price_block": price_brake["block"],
            "price_blocks": price_brake["blocks"],
            "price_block_start": block_start,
            "price_block_end": block_end,
            "in_price_block": in_price_block,
            "block_state": block_state,
            "active_block_index": active_block_index,
            "block_windows": block_windows,
            "price_rate_limited": rate_limited,
            "comfort_push": comfort_output,
            "comfort_I": self._comfort_integral,
            "comfort_saturated_high": comfort_high,
            "comfort_saturated_low": comfort_low,
            "temp_error": temp_error,
            "dt_minutes": dt_minutes,
            "brake_blocked_reason": brake_blocked_reason,
        }

    def _apply_control_bias(
        self, fake_temp: float, sensor_data: Dict[str, Any], pi_data: Dict[str, Any]
    ) -> Tuple[float, float]:
        """Apply PI-based control bias to the fake temperature."""
        aggressiveness_factor = min(1.0, max(0.0, sensor_data["aggressiveness"] / 5.0))
        gas_component = max(pi_data["comfort_push"], 0.0)
        backoff_component = max(-pi_data["comfort_push"], 0.0)
        brake_component = pi_data["price_brake_level"]

        final_adjust = (
            GAS_WEIGHT * gas_component
            - BRAKE_WEIGHT * brake_component
            - COMFORT_BACKOFF_WEIGHT * backoff_component
        )
        final_adjust = max(-1.0, min(1.0, final_adjust))
        temp_bias = -final_adjust * CONTROL_BIAS_TEMP_SCALE * aggressiveness_factor

        adjusted = fake_temp + temp_bias
        adjusted = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, adjusted))
        return adjusted, final_adjust

    def _log_control_debug(self, pi_data: Dict[str, Any], final_adjust: float) -> None:
        """Log control status at a controlled rate."""
        now = dt_util.now()
        if self._last_debug_log and (now - self._last_debug_log).total_seconds() < 600:
            return
        self._last_debug_log = now
        block = pi_data["price_block"]
        block_start = block.start_offset_minutes if block else None
        block_end = block.end_offset_minutes if block else None
        _LOGGER.debug(
            "Price brake: baseline=%.3f threshold=%.3f area=%.3f amplitude=%.3f "
            "brake=%.3f block_start=%s block_end=%s dt=%s min rate_limited=%s "
            "comfort=%.3f temp_error=%.2f adjust=%.3f",
            pi_data["price_baseline"],
            pi_data["price_threshold"],
            pi_data["price_area"],
            pi_data["price_amplitude"],
            pi_data["price_brake_level"],
            block_start,
            block_end,
            pi_data["dt_minutes"],
            pi_data["price_rate_limited"],
            pi_data["comfort_push"],
            pi_data["temp_error"],
            final_adjust,
        )

    def _calculate_output_temperature(
        self,
        sensor_data: Dict[str, Any],
        price_category: str,
        current_slot_index: int,
    ) -> Tuple[float, str]:
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
            _LOGGER.info(
                "Activating summer precool mode due to forecasted high temperatures"
            )
            return BRAKE_FAKE_TEMP, "precool"

        if outdoor_temp >= summer_threshold:
            return outdoor_temp, "summer_mode"

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

        if abs(temp_diff) <= NEUTRAL_TEMP_THRESHOLD:
            fake_temp = outdoor_temp
            mode = "neutral"
        else:
            fake_temp, mode = calculate_temperature_output(
                indoor_temp,
                target_temp_for_logic,
                outdoor_temp,
                aggressiveness,
                brake_temp,
            )

        fake_temp = min(fake_temp, BRAKE_FAKE_TEMP)
        return fake_temp, mode

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
            "aggressiveness": sensor_data.get("aggressiveness", 0),
            "inertia": sensor_data.get("inertia"),
            "mode": mode,
            "fake_temp": fake_temp,
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
    ) -> Tuple[List[float], float, str, List[str], int, int]:
        """Fetch price data and classify prices"""
        entity_id = config.get("electricity_price_entity")

        if not entity_id:
            _LOGGER.error("No electricity price entity configured")
            return [], 0.0, "unknown", [], 60, 0

        prices_raw = get_attr(self.hass, entity_id, "today") or get_attr(
            self.hass, entity_id, "raw_today"
        )
        if not prices_raw:
            _LOGGER.warning("Could not retrieve electricity prices from %s", entity_id)
            return [], 0.0, "unknown", [], 60, 0

        try:
            prices = [
                float(p)
                for p in prices_raw
                if isinstance(p, (float, int)) and p is not None
            ]
        except (ValueError, TypeError) as e:
            _LOGGER.error("Error converting prices to float: %s", e)
            return [], 0.0, "unknown", [], 60, 0

        if not prices:
            _LOGGER.warning("No valid prices found after conversion")
            return [], 0.0, "unknown", [], 60, 0

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

        current_price, price_category = safe_get_current_price_and_category(
            prices, categories, current_slot_index, mode
        )

        return (
            prices,
            current_price,
            price_category,
            categories,
            price_interval_minutes,
            current_slot_index,
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
        pi_data: Dict[str, Any],
        final_adjust: float,
        update_time: datetime,
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

        block_windows = pi_data["block_windows"]
        active_block_index = pi_data["active_block_index"]
        blocks_detected = len(pi_data["price_blocks"])
        block_detected = blocks_detected > 0
        next_block_start = (
            pi_data["price_block_start"].isoformat()
            if pi_data["price_block_start"]
            else None
        )
        next_block_end = (
            pi_data["price_block_end"].isoformat()
            if pi_data["price_block_end"]
            else None
        )
        next_block = None
        if pi_data["price_block_start"] and pi_data["price_block_end"]:
            for block, block_start, block_end in block_windows:
                if (
                    block_start == pi_data["price_block_start"]
                    and block_end == pi_data["price_block_end"]
                ):
                    next_block = block
                    break
        active_block = None
        if 0 < active_block_index <= len(block_windows):
            active_block = block_windows[active_block_index - 1][0]
        duration_source = next_block or active_block
        duration_minutes = duration_source.duration_minutes if duration_source else 0
        peak_price = duration_source.peak if duration_source else 0.0

        block_1 = block_windows[0] if len(block_windows) > 0 else None
        block_2 = block_windows[1] if len(block_windows) > 1 else None

        attributes = {
            "mode": mode,
            "fake_outdoor_temperature": self._attr_native_value,
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
            "last_updated": update_time.isoformat(),
            "temp_error_c": round(
                sensor_data["indoor_temp"] - sensor_data["target_temp"], 2
            ),
            "to_summer_threshold_c": round(
                sensor_data["summer_threshold"] - sensor_data["outdoor_temp"], 2
            ),
            "saving_potential_sek_per_kwh": round(max_price - current_price, 3),
            "decision_reason": decision_reason,
            "current_hour": now_hour,
            "current_price_slot_index": current_slot_index,
            "price_interval_minutes": price_interval_minutes,
            "price_brake_level": round(pi_data["price_brake_level"], 3),
            "baseline": round(pi_data["price_baseline"], 3),
            "threshold": round(pi_data["price_threshold"], 3),
            "area": round(pi_data["price_area"], 3),
            "amplitude": round(pi_data["price_amplitude"], 3),
            "next_block_start": next_block_start,
            "next_block_end": next_block_end,
            "duration_minutes": duration_minutes,
            "peak_price": round(peak_price, 3),
            "block_detected": block_detected,
            "blocks_detected": blocks_detected,
            "block_1_start": block_1[1].isoformat() if block_1 else None,
            "block_1_end": block_1[2].isoformat() if block_1 else None,
            "block_1_peak": round(block_1[0].peak, 3) if block_1 else None,
            "block_1_area": round(block_1[0].area, 3) if block_1 else None,
            "block_1_duration_minutes": block_1[0].duration_minutes if block_1 else 0,
            "block_2_start": block_2[1].isoformat() if block_2 else None,
            "block_2_end": block_2[2].isoformat() if block_2 else None,
            "block_2_peak": round(block_2[0].peak, 3) if block_2 else None,
            "block_2_area": round(block_2[0].area, 3) if block_2 else None,
            "block_2_duration_minutes": block_2[0].duration_minutes if block_2 else 0,
            "in_price_block": pi_data["in_price_block"],
            "block_state": pi_data["block_state"],
            "active_block_index": active_block_index,
            "comfort_push": round(pi_data["comfort_push"], 3),
            "temp_error": round(pi_data["temp_error"], 3),
            "comfort_pi_kp": COMFORT_PI_KP,
            "comfort_pi_ki": COMFORT_PI_KI,
            "comfort_I": round(pi_data["comfort_I"], 4),
            "final_adjust": round(final_adjust, 3),
            "price_rate_limited": pi_data["price_rate_limited"],
            "rate_limited": pi_data["price_rate_limited"],
            "brake_blocked_reason": pi_data["brake_blocked_reason"],
            "data_quality": {
                "prices_count": len(prices),
                "categories_count": len(categories),
                "forecast_available": bool(sensor_data["outdoor_temp_forecast_entity"]),
            },
        }

        return attributes

    def _update_diagnostics(
        self,
        prices: List[float],
        categories: List[str],
        next_3_hours_prices: List[float],
        price_interval_minutes: int,
        current_slot_index: int,
        update_time: datetime,
    ) -> None:
        """Update diagnostics data with large debug arrays."""
        self._diagnostics.clear()
        self._diagnostics.update(
            {
                "price_categories_all_hours": categories,
                "next_3_hours_prices": next_3_hours_prices,
                "price_interval_minutes": price_interval_minutes,
                "current_price_slot_index": current_slot_index,
                "prices_count": len(prices),
                "last_updated": update_time.isoformat(),
            }
        )

    async def async_update(self) -> None:
        """Update sensor data"""

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
        ) = await self._get_price_data(config, update_time)
        self._last_price_category = price_category

        missing = self._validate_required_data(sensor_data, prices)
        if missing:
            self._attr_native_value = None
            self._attr_available = False
            self._attributes = {
                "Status": f"Missing: {', '.join(missing)}",
                "Last Updated": update_time.isoformat(),
                "Current Hour": now_hour,
            }
            self._diagnostics.clear()
            return
        self._attr_available = True

        holiday = is_holiday_mode_active(
            self.hass,
            HARDCODED_ENTITIES["holiday_mode_boolean_entity"],
            HARDCODED_ENTITIES["holiday_start_datetime_entity"],
            HARDCODED_ENTITIES["holiday_end_datetime_entity"],
        )

        if holiday:
            sensor_data["target_temp"] = HOLIDAY_TEMP

        combined_prices = self._get_combined_prices(
            config.get("electricity_price_entity", "")
        )
        pi_data = self._compute_controls(
            sensor_data,
            combined_prices,
            current_slot_index,
            price_interval_minutes,
            config,
            current_price,
            price_category,
            update_time,
        )

        fake_temp, mode = self._calculate_output_temperature(
            sensor_data,
            price_category,
            current_slot_index,
        )
        if (
            mode == "neutral"
            and pi_data["price_brake_level"] > 0.0
            and pi_data["brake_blocked_reason"]
            in {"allowed", "rate_limited", "expensive_now"}
        ):
            mode = "braking_by_price"
        adjusted_temp, final_adjust = self._apply_control_bias(
            fake_temp, sensor_data, pi_data
        )
        self._attr_native_value = round(fake_temp, 1)

        next_3_hours_prices = get_price_window_for_hours(
            prices,
            current_slot_index,
            3,
            price_interval_minutes,
        )
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
            pi_data,
            final_adjust,
            update_time,
        )
        self._update_diagnostics(
            prices,
            categories,
            next_3_hours_prices,
            price_interval_minutes,
            current_slot_index,
            update_time,
        )

        self._log_control_debug(pi_data, final_adjust)

        if self.ml_collector:
            self._collect_ml_data(sensor_data, mode, adjusted_temp)

        self._last_update_time = update_time


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PumpSteer sensor entity"""
    sensor = PumpSteerSensor(hass, config_entry)
    async_add_entities([sensor], update_before_add=True)
