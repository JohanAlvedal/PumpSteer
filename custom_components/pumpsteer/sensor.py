import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.components.sensor import SensorEntity

from .control import PIController
from .electricity_price import (
    PRICE_EXPENSIVE,
    PRICE_NORMAL,
    async_get_price_thresholds,
    classify_price_list,
    filter_short_peaks,
)
from .holiday import async_update_holiday
from .ohmigo import async_push_ohmigo
from .pump_log import log_event, log_mode_change
from .settings import (
    BRAKE_DELTA_C,
    BRAKE_HOLD_MINUTES,
    COMFORT_FLOOR_BY_AGGRESSIVENESS,
    DEFAULT_AGGRESSIVENESS,
    DEFAULT_HOUSE_INERTIA,
    DEFAULT_SUMMER_THRESHOLD,
    DEFAULT_TARGET_TEMP,
    HOLIDAY_TEMP,
    MAX_FAKE_TEMP,
    MIN_FAKE_TEMP,
    PEAK_FILTER_MIN_DURATION_MINUTES,
    PID_INTEGRAL_CLAMP,
    PID_KD,
    PID_KI,
    PID_KP,
    PID_OUTPUT_CLAMP,
    PRECOOL_LOOKAHEAD,
    PRECOOL_MARGIN,
    PREHEAT_BOOST_C,
    PREHEAT_ON_MISSING_FORECAST,
    PRICE_LOOKAHEAD_HOURS,
    RAMP_OUT_FACTOR,
    RAMP_MAX_MINUTES,
    RAMP_MIN_MINUTES,
    RAMP_SCALE,
)
from .utils import (
    compute_price_slot_index,
    detect_price_interval_minutes,
    get_attr,
    get_state,
    get_version,
    safe_float,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"
SW_VERSION = get_version()

# Operating modes.
MODE_SUMMER = "summer_mode"
MODE_PRECOOL = "precool"
MODE_PREHEAT = "preheating"
MODE_PREBRAKE = "pre_braking"
MODE_BRAKING = "braking"
MODE_PI = "normal"
MODE_HOLIDAY = "holiday"
MODE_ERROR = "error"
MODE_SAFE = "safe_mode"

_RESTORE_BRAKE_RAMP = "brake_ramp"
_RESTORE_BRAKE_LAST_T = "brake_last_t"
_RESTORE_BRAKE_LAST_EXPENSIVE_T = "brake_last_expensive_t"

# Maximum dt_seconds allowed in _update_brake_ramp.
# Caps the step size so a long gap between mode transitions (e.g. normal →
# braking at a slot boundary, or braking → normal when price is reclassified)
# does not cause a large jump in brake_ramp in a single cycle.
# 60 s = one polling cycle → max ±5% per step at ramp_in/out = 20 min.
_BRAKE_RAMP_MAX_DT_SECONDS: float = 60.0


class PumpSteerSensor(RestoreEntity):
    """
    PumpSteer heat pump controller.

    State machine:
        summer_mode  -> outdoor >= summer_threshold, passthrough
        precool      -> forecast shows warm period coming, raise fake temp
        holiday      -> lower target, same PI/braking logic
        preheating   -> expensive period coming, boost heating now
        braking      -> expensive period active, PI disconnected
        normal       -> PI regulates fake temp toward target
        safe_mode    -> required data missing, passthrough real outdoor temp
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self._config_entry = config_entry
        self._state: Optional[float] = None
        self._attributes: Dict[str, Any] = {}
        self._ohmigo_last_push = None

        self._pi = PIController()

        self._brake_ramp: float = 0.0
        self._preheat_ramp: float = 0.0
        self._brake_last_t: Optional[datetime] = None
        self._brake_last_expensive_t: Optional[datetime] = None
        self._ramp_in_minutes: float = 15.0
        self._ramp_out_minutes: float = 15.0

        self._last_price_categories: List[str] = []
        self._p30: float = 0.0
        self._p80: float = 0.0

        # Cache price thresholds once per calendar day per entity.
        # Recomputing every hour caused mid-slot reclassification: P80 could
        # shift just enough to flip an ongoing expensive slot to normal,
        # releasing the brake unexpectedly. Caching per day means thresholds
        # are stable throughout the day and only refresh when new price data
        # arrives at midnight.
        self._price_thresholds_cached_date: Optional[str] = None  # "YYYY-MM-DD"
        self._price_thresholds_entity_id: Optional[str] = None
        self._cached_p30: float = 0.0
        self._cached_p80: float = 0.0

        # Track previous aggressiveness to detect transition into aggressiveness=0.
        # The PI reset should happen once on entry, not on every cycle.
        self._prev_aggressiveness: Optional[int] = None
        self._prev_mode: Optional[str] = None

        # Store the remove callback returned by add_update_listener so it can
        # be cleaned up on unload.
        self._remove_update_listener = None

        self._attr_unique_id = config_entry.entry_id
        self._forecast_available_last: Optional[bool] = None
        self._safe_mode_warned: bool = False
        self._helper_fallback_issues: Dict[str, Optional[str]] = {
            "target_temperature": None,
            "summer_threshold": None,
            "aggressiveness": None,
            "house_inertia": None,
        }
        self._price_issue: Optional[str] = None
        self._attr_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"
        self._attr_state_class = "measurement"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="PumpSteer",
            model="Heat Pump Controller",
            sw_version=SW_VERSION,
        )

    @property
    def name(self) -> str:
        return "PumpSteer"

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
        return self._state is not None

    @property
    def should_poll(self) -> bool:
        return True

    @property
    def extra_restore_state_data(self):
        """Persist brake ramp state across restarts."""
        from homeassistant.helpers.restore_state import ExtraStoredData

        class _BrakeData(ExtraStoredData):
            def __init__(self, brake_ramp, brake_last_t, brake_last_expensive_t):
                self.brake_ramp = brake_ramp
                self.brake_last_t = brake_last_t
                self.brake_last_expensive_t = brake_last_expensive_t

            def as_dict(self):
                return {
                    _RESTORE_BRAKE_RAMP: self.brake_ramp,
                    _RESTORE_BRAKE_LAST_T: (
                        self.brake_last_t.isoformat() if self.brake_last_t else None
                    ),
                    _RESTORE_BRAKE_LAST_EXPENSIVE_T: (
                        self.brake_last_expensive_t.isoformat()
                        if self.brake_last_expensive_t
                        else None
                    ),
                }

        return _BrakeData(
            self._brake_ramp,
            self._brake_last_t,
            self._brake_last_expensive_t,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        self._remove_update_listener = self._config_entry.add_update_listener(
            self.async_options_update_listener
        )

        # Restore basic state (fake temp + attributes).
        last = await self.async_get_last_state()
        if last is not None:
            restored = safe_float(last.state)
            if restored is not None:
                self._state = restored
                self._attributes = {
                    key: value
                    for key, value in last.attributes.items()
                    if key != "friendly_name"
                }

        # Restore brake ramp state so braking survives HA restarts.
        extra = await self.async_get_last_extra_data()
        if extra is not None:
            data = extra.as_dict()
            self._brake_ramp = float(data.get(_RESTORE_BRAKE_RAMP, 0.0))
            raw_last_t = data.get(_RESTORE_BRAKE_LAST_T)
            raw_last_exp = data.get(_RESTORE_BRAKE_LAST_EXPENSIVE_T)
            try:
                self._brake_last_t = (
                    datetime.fromisoformat(raw_last_t) if raw_last_t else None
                )
            except (ValueError, TypeError):
                self._brake_last_t = None
            try:
                self._brake_last_expensive_t = (
                    datetime.fromisoformat(raw_last_exp) if raw_last_exp else None
                )
            except (ValueError, TypeError):
                self._brake_last_expensive_t = None
            _LOGGER.debug(
                "PumpSteer restored brake state: ramp=%.3f last_t=%s last_exp=%s",
                self._brake_ramp,
                self._brake_last_t,
                self._brake_last_expensive_t,
            )

        # Wait until Home Assistant is fully started before the first real update.
        self.hass.bus.async_listen_once(
            "homeassistant_started",
            self._handle_ha_started,
        )

        # If HA is already running (for example on reload), update immediately.
        if self.hass.is_running:
            await self.async_update()
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel options update listener on unload."""
        if self._remove_update_listener is not None:
            self._remove_update_listener()
            self._remove_update_listener = None
        await super().async_will_remove_from_hass()

    async def async_options_update_listener(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Handle updated options."""
        self._config_entry = entry
        await self.async_update()

    async def _handle_ha_started(self, event) -> None:
        """Run when HA is fully started and entities are ready."""
        await self.async_update()
        self.async_write_ha_state()

    def _cfg(self) -> Dict[str, Any]:
        return {**self._config_entry.data, **self._config_entry.options}

    def _read_entity(
        self,
        entity_id: str,
        default: Optional[float] = None,
    ) -> Optional[float]:
        return safe_float(get_state(self.hass, entity_id)) if entity_id else default

    def _number_entity_id(self, key: str) -> Optional[str]:
        """Look up entity_id for a PumpSteer NumberEntity by its unique_id."""
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            "number", DOMAIN, f"{self._config_entry.entry_id}_{key}"
        )

    def _aggressiveness(self, cfg: Dict[str, Any]) -> int:
        value = self._helper_value_with_fallback(
            helper_key="aggressiveness",
            cfg=cfg,
            default=float(DEFAULT_AGGRESSIVENESS),
        )
        return max(0, min(5, int(round(float(value)))))

    def _house_inertia(self, cfg: Dict[str, Any]) -> float:
        value = self._helper_value_with_fallback(
            helper_key="house_inertia",
            cfg=cfg,
            default=float(DEFAULT_HOUSE_INERTIA),
        )
        return max(0.5, min(10.0, float(value)))

    def _set_helper_issue(self, helper_key: str, issue: str, message: str) -> None:
        """Warn once per helper issue and downgrade repeats to debug."""
        previous = self._helper_fallback_issues.get(helper_key)
        if previous != issue:
            _LOGGER.warning(message)
            self._helper_fallback_issues[helper_key] = issue
        else:
            _LOGGER.debug(message)

    def _clear_helper_issue(self, helper_key: str, entity_id: Optional[str]) -> None:
        """Log helper recovery once when a fallback issue clears."""
        previous = self._helper_fallback_issues.get(helper_key)
        if previous is not None:
            _LOGGER.info(
                "PumpSteer helper '%s' recovered and now uses %s",
                helper_key,
                entity_id or "configured option value",
            )
            self._helper_fallback_issues[helper_key] = None

    def _helper_value_with_fallback(
        self,
        helper_key: str,
        cfg: Dict[str, Any],
        default: float,
    ) -> float:
        """Read helper value with warn-once fallback logging."""
        cfg_raw = cfg.get(helper_key)
        if cfg_raw is not None:
            parsed_cfg = safe_float(cfg_raw)
            if parsed_cfg is not None:
                self._clear_helper_issue(helper_key, None)
                return parsed_cfg
            self._set_helper_issue(
                helper_key,
                "invalid_option",
                (
                    f"PumpSteer helper '{helper_key}' has invalid configured value "
                    f"'{cfg_raw}', falling back to default {default}"
                ),
            )
            return default

        entity_id = self._number_entity_id(helper_key)
        if not entity_id:
            self._set_helper_issue(
                helper_key,
                "missing_entity",
                (
                    f"PumpSteer helper '{helper_key}' has no number entity "
                    f"(entry_id={self._config_entry.entry_id}), falling back to default "
                    f"{default}"
                ),
            )
            return default

        state_obj = self.hass.states.get(entity_id)
        if state_obj is None:
            self._set_helper_issue(
                helper_key,
                "entity_not_found",
                (
                    f"PumpSteer helper '{helper_key}' entity '{entity_id}' not found, "
                    f"falling back to default {default}"
                ),
            )
            return default

        state_raw = state_obj.state
        if state_raw in ("unknown", "unavailable", None):
            self._set_helper_issue(
                helper_key,
                "temporarily_unavailable",
                (
                    f"PumpSteer helper '{helper_key}' entity '{entity_id}' is "
                    f"temporarily unavailable (state={state_raw}), falling back to "
                    f"default {default}"
                ),
            )
            return default

        parsed = safe_float(state_raw)
        if parsed is None:
            self._set_helper_issue(
                helper_key,
                "invalid_state",
                (
                    f"PumpSteer helper '{helper_key}' entity '{entity_id}' has invalid "
                    f"state '{state_raw}', falling back to default {default}"
                ),
            )
            return default

        self._clear_helper_issue(helper_key, entity_id)
        return parsed

    def _set_price_issue(self, issue: str, message: str) -> None:
        """Warn once per price issue and downgrade repeats to debug."""
        if self._price_issue != issue:
            _LOGGER.warning(message)
            self._price_issue = issue
        else:
            _LOGGER.debug(message)

    def _clear_price_issue(self, today_entity_id: str, tomorrow_entity_id: str) -> None:
        """Log price data recovery once when an issue clears."""
        if self._price_issue is not None:
            _LOGGER.info(
                "PumpSteer price data recovered for today='%s', tomorrow='%s'",
                today_entity_id,
                tomorrow_entity_id,
            )
            self._price_issue = None

    def _comfort_floor(self, target: float, aggressiveness: int) -> float:
        drop = COMFORT_FLOOR_BY_AGGRESSIVENESS[aggressiveness]
        return target - drop

    def _brake_temp(self, outdoor: float, delta_c: Optional[float] = None) -> float:
        delta = delta_c if delta_c is not None else BRAKE_DELTA_C
        return min(max(outdoor + delta, MIN_FAKE_TEMP), MAX_FAKE_TEMP)

    def _compute_ramp_minutes(self, house_inertia: float) -> float:
        ramp = house_inertia * RAMP_SCALE
        return max(RAMP_MIN_MINUTES, min(RAMP_MAX_MINUTES, ramp))

    def _next_period_category(
        self,
        categories: List[str],
        current_slot: int,
        interval_minutes: int,
    ) -> Optional[str]:
        del interval_minutes
        next_slot = current_slot + 1
        if next_slot < len(categories):
            return categories[next_slot]
        return None

    def _minutes_until_expensive(
        self,
        categories: List[str],
        current_slot: int,
        interval_minutes: int,
        now: datetime,
    ) -> Optional[float]:
        for index in range(1, len(categories) - current_slot):
            if categories[current_slot + index] == PRICE_EXPENSIVE:
                minutes_into_slot = now.minute % interval_minutes
                minutes_left_in_slot = interval_minutes - minutes_into_slot
                minutes_total = minutes_left_in_slot + (index - 1) * interval_minutes
                return float(minutes_total)
        return None

    def _upcoming_expensive(
        self,
        categories: List[str],
        current_slot: int,
        lookahead_slots: int,
    ) -> bool:
        for index in range(
            current_slot + 1,
            min(len(categories), current_slot + lookahead_slots + 1),
        ):
            if categories[index] == PRICE_EXPENSIVE:
                return True
        return False

    async def _forecast_temps(self) -> Optional[List[float]]:
        cfg = self._cfg()
        weather_entity = cfg.get("weather_entity")
        price_entity = cfg.get("electricity_price_entity")

        if not weather_entity or not price_entity:
            if self._forecast_available_last is not False:
                _LOGGER.debug(
                    "PumpSteer forecast unavailable: %s",
                    (
                        "weather_entity not configured"
                        if not weather_entity
                        else "electricity_price_entity not configured"
                    ),
                )
                self._forecast_available_last = False
            return None

        from .forecast import async_build_forecast

        try:
            points = await async_build_forecast(
                self.hass,
                price_entity_id=price_entity,
                weather_entity_id=weather_entity,
                horizon_hours=PRECOOL_LOOKAHEAD,
            )
        except Exception as err:
            if self._forecast_available_last is not False:
                _LOGGER.debug("PumpSteer forecast build failed: %s", err)
                self._forecast_available_last = False
            return None

        temps = [p.outdoor_temp for p in points if p.outdoor_temp is not None]
        available_now = bool(temps)

        if available_now != self._forecast_available_last:
            if available_now:
                _LOGGER.debug(
                    "PumpSteer forecast available (weather=%s, %d points)",
                    weather_entity,
                    len(temps),
                )
            else:
                _LOGGER.debug(
                    "PumpSteer forecast returned no usable temperatures "
                    "(weather=%s, price=%s)",
                    weather_entity,
                    price_entity,
                )
            self._forecast_available_last = available_now

        return temps if temps else None

    def _should_precool(
        self, summer_threshold: float, temps: Optional[List[float]]
    ) -> bool:
        if not temps:
            return False
        return any(temp >= summer_threshold + PRECOOL_MARGIN for temp in temps)

    def _forecast_is_cold(
        self, summer_threshold: float, temps: Optional[List[float]], hours: int = 6
    ) -> bool:
        if not temps:
            if PREHEAT_ON_MISSING_FORECAST:
                _LOGGER.debug(
                    "_forecast_is_cold: no forecast, assuming cold "
                    "(PREHEAT_ON_MISSING_FORECAST=True)"
                )
            else:
                _LOGGER.debug(
                    "_forecast_is_cold: no forecast, assuming not cold "
                    "(PREHEAT_ON_MISSING_FORECAST=False)"
                )
            return PREHEAT_ON_MISSING_FORECAST

        window = temps[:hours]
        cold_hours = sum(1 for temp in window if temp < summer_threshold)
        return cold_hours >= max(1, len(window) // 2)

    def _base_attrs(
        self,
        indoor: float,
        target: float,
        outdoor: float,
        price_category: str,
        aggressiveness: int,
        heating_demand_c: float = 0.0,
    ) -> Dict[str, Any]:
        """Return standard attributes included in all modes."""
        return {
            "heating_demand_c": round(heating_demand_c, 2),
            "indoor_temperature": indoor,
            "target_temperature": target,
            "outdoor_temperature": outdoor,
            "price_category": price_category,
            "aggressiveness": aggressiveness,
            "p30": round(self._p30, 3),
            "p80": round(self._p80, 3),
        }

    def _enter_safe_mode(
        self,
        reason: str,
        outdoor: Optional[float],
        now: datetime,
    ) -> None:
        if not self._safe_mode_warned:
            _LOGGER.warning(
                "PumpSteer entered SAFE MODE: %s — optimization paused, sending real outdoor temp",
                reason,
            )
            self._safe_mode_warned = True
            log_event("SAFE_MODE_ENTER", reason=reason)
        else:
            _LOGGER.debug("PumpSteer safe mode still active: %s", reason)

        self._pi.reset(now)
        self._brake_ramp = 0.0
        self._preheat_ramp = 0.0
        self._brake_last_t = None
        self._brake_last_expensive_t = None

        if outdoor is not None:
            self._state = round(outdoor, 1)
            self._attributes = {
                "mode": MODE_SAFE,
                "fake_outdoor_temperature": self._state,
                "status": f"safe_mode: {reason}",
                "last_updated": now.isoformat(),
                "outdoor_temperature": outdoor,
            }
        else:
            self._state = None
            self._attributes = {
                "mode": MODE_SAFE,
                "status": f"safe_mode (no data): {reason}",
                "last_updated": now.isoformat(),
            }

    def _update_brake_ramp(
        self,
        brake_requested: bool,
        now: datetime,
        ramp_in: float,
        ramp_out: float,
        hold_minutes: float = BRAKE_HOLD_MINUTES,
    ) -> float:
        """Update brake ramp factor with optional hold time.

        dt_seconds is capped to _BRAKE_RAMP_MAX_DT_SECONDS (60 s) so that a
        long gap between polling cycles — e.g. at a mode transition or after an
        HA restart — never causes a large jump in brake_ramp in a single step.
        This applies equally to ramp-in and ramp-out.
        """
        if self._brake_last_t is None:
            dt_seconds = _BRAKE_RAMP_MAX_DT_SECONDS
        else:
            dt_seconds = max((now - self._brake_last_t).total_seconds(), 1.0)
            dt_seconds = min(dt_seconds, _BRAKE_RAMP_MAX_DT_SECONDS)

        self._brake_last_t = now

        if brake_requested:
            self._brake_last_expensive_t = now
            rate = 1.0 / (ramp_in * 60.0)
            self._brake_ramp += dt_seconds * rate
        else:
            hold_active = (
                self._brake_last_expensive_t is not None
                and (now - self._brake_last_expensive_t).total_seconds()
                < hold_minutes * 60.0
            )
            if not hold_active:
                rate = 1.0 / (ramp_out * 60.0)
                self._brake_ramp -= dt_seconds * rate

        self._brake_ramp = max(0.0, min(1.0, self._brake_ramp))
        return self._brake_ramp

    def _update_preheat_ramp(
        self,
        preheat_requested: bool,
        ramp_in: float,
        ramp_out: float,
    ) -> float:
        """Update preheat ramp factor for smooth preheat entry and exit."""
        step_up = 1.0 / max(ramp_in, 1.0)
        step_down = 1.0 / max(ramp_out, 1.0)

        if preheat_requested:
            self._preheat_ramp += step_up
        else:
            self._preheat_ramp -= step_down

        self._preheat_ramp = max(0.0, min(1.0, self._preheat_ramp))
        return self._preheat_ramp

    def _pi_output(
        self,
        target: float,
        indoor: float,
        outdoor: float,
        now: datetime,
        cfg: Dict[str, Any],
        freeze_integral: bool = False,
    ) -> float:
        """Compute heating demand from the PI controller."""
        kp = float(cfg.get("pid_kp", PID_KP))
        ki = float(cfg.get("pid_ki", PID_KI))
        kd = float(cfg.get("pid_kd", PID_KD))
        integral_clamp = float(cfg.get("pid_integral_clamp", PID_INTEGRAL_CLAMP))
        output_clamp = float(cfg.get("pid_output_clamp", PID_OUTPUT_CLAMP))

        result = self._pi.compute(
            target_temp=target,
            indoor_temp=indoor,
            outdoor_temp=outdoor,
            aggressiveness=1.0,
            update_time=now,
            braking_active=freeze_integral,
            kp=kp,
            ki=ki,
            kd=kd,
            feedforward_bias=0.0,
            integral_clamp=integral_clamp,
            output_clamp=output_clamp,
            min_fake_temp=MIN_FAKE_TEMP,
            max_fake_temp=MAX_FAKE_TEMP,
            brake_behavior="freeze",
            decay_per_minute_on_brake=0.98,
        )
        return -result.offset

    async def async_update(self) -> None:
        """Update sensor state."""
        try:
            await self._do_update()
        except Exception as err:
            _LOGGER.exception("PumpSteer update failed: %s", err)
            self._state = None
            self._attributes = {
                "status": "error",
                "last_error": str(err),
                "last_updated": dt_util.now().isoformat(),
            }

    async def _do_update(self) -> None:
        """Run the main control state machine."""
        now = dt_util.now()
        cfg = self._cfg()

        indoor = safe_float(get_state(self.hass, cfg.get("indoor_temp_entity")))
        outdoor = safe_float(get_state(self.hass, cfg.get("real_outdoor_entity")))
        target = self._helper_value_with_fallback(
            helper_key="target_temperature",
            cfg=cfg,
            default=float(DEFAULT_TARGET_TEMP),
        )
        summer_threshold = self._helper_value_with_fallback(
            helper_key="summer_threshold",
            cfg=cfg,
            default=float(DEFAULT_SUMMER_THRESHOLD),
        )
        aggressiveness = self._aggressiveness(cfg)
        house_inertia = self._house_inertia(cfg)

        if indoor is None or outdoor is None:
            missing = []
            if indoor is None:
                missing.append(
                    f"indoor sensor '{cfg.get('indoor_temp_entity') or 'not configured'}'"
                )
            if outdoor is None:
                missing.append(
                    f"outdoor sensor '{cfg.get('real_outdoor_entity') or 'not configured'}'"
                )
            self._enter_safe_mode(
                "Missing sensors: " + ", ".join(missing),
                outdoor,
                now,
            )
            return

        holiday = await async_update_holiday(
            self.hass, self._config_entry.entry_id, self._config_entry
        )
        if holiday:
            target = HOLIDAY_TEMP

        prices, categories, interval_minutes, current_slot = await self._get_prices(
            cfg,
            now,
        )

        if not prices:
            today_entity_id = cfg.get("electricity_price_entity") or "not configured"
            tomorrow_entity_id = cfg.get("price_tomorrow_entity") or today_entity_id
            self._enter_safe_mode(
                f"No price data from today='{today_entity_id}', "
                f"tomorrow='{tomorrow_entity_id}'",
                outdoor,
                now,
            )
            return

        current_cat = categories[current_slot] if categories else PRICE_NORMAL
        next_cat = self._next_period_category(
            categories, current_slot, interval_minutes
        )

        lookahead_slots = max(
            1,
            math.ceil((PRICE_LOOKAHEAD_HOURS * 60) / max(interval_minutes, 1)),
        )

        # ramp_in/out derived directly from house_inertia — independent of price jump.
        # Higher thermal mass = longer ramp, giving a heavier house more time to respond.
        upcoming = self._upcoming_expensive(categories, current_slot, lookahead_slots)
        ramp_in = self._compute_ramp_minutes(house_inertia)
        ramp_out = max(RAMP_MIN_MINUTES, ramp_in * RAMP_OUT_FACTOR)

        comfort_floor = self._comfort_floor(target, aggressiveness)
        forecast_temps = await self._forecast_temps()

        # 1. Summer mode.
        if outdoor >= summer_threshold:
            self._pi.reset(now)
            self._brake_ramp = 0.0
            self._preheat_ramp = 0.0
            self._brake_last_t = None
            self._prev_aggressiveness = None

            fake_temp = outdoor
            await self._set_state(
                fake_temp,
                MODE_SUMMER,
                {
                    **self._base_attrs(
                        indoor,
                        target,
                        outdoor,
                        current_cat,
                        aggressiveness,
                    ),
                    "summer_threshold": summer_threshold,
                },
                now,
            )
            return

        # 2. Precool.
        if self._should_precool(summer_threshold, forecast_temps):
            brake_temp = self._brake_temp(outdoor)
            factor = self._update_brake_ramp(
                True,
                now,
                ramp_in=10.0,
                ramp_out=20.0,
            )
            fake_temp = outdoor + (brake_temp - outdoor) * factor
            fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, fake_temp))

            await self._set_state(
                fake_temp,
                MODE_PRECOOL,
                {
                    **self._base_attrs(
                        indoor,
                        target,
                        outdoor,
                        current_cat,
                        aggressiveness,
                    ),
                    "brake_factor": round(factor, 3),
                },
                now,
            )
            return

        # 3. Aggressiveness 0 -> pure PI, no price logic.
        if aggressiveness == 0:
            if self._prev_aggressiveness != 0:
                _LOGGER.debug(
                    "Aggressiveness changed to 0 (was %s): resetting PI integral once",
                    self._prev_aggressiveness,
                )
                self._pi.reset(now)
                self._brake_ramp = 0.0
                self._preheat_ramp = 0.0
                self._brake_last_t = None

            self._prev_aggressiveness = 0

            demand = self._pi_output(target, indoor, outdoor, now, cfg)
            fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - demand))

            await self._set_state(
                fake_temp,
                MODE_PI,
                {
                    **self._base_attrs(indoor, target, outdoor, current_cat, 0, demand),
                    "note": "Price control disabled (aggressiveness=0)",
                },
                now,
            )
            return

        self._prev_aggressiveness = aggressiveness

        # 4. Braking during expensive period.
        if current_cat == PRICE_EXPENSIVE:
            brake_delta = float(cfg.get("brake_delta_c", BRAKE_DELTA_C))
            brake_hold = float(cfg.get("brake_hold_minutes", BRAKE_HOLD_MINUTES))

            if indoor < comfort_floor:
                _LOGGER.info(
                    "Comfort floor reached (%.1f < %.1f), releasing brake",
                    indoor,
                    comfort_floor,
                )
                log_event("COMFORT_FLOOR_RELEASE", indoor=round(indoor, 1), floor=round(comfort_floor, 1))
                brake_requested = False
                brake_hold = 0.0
            else:
                brake_requested = True

            factor = self._update_brake_ramp(
                brake_requested,
                now,
                ramp_in,
                ramp_out,
                hold_minutes=brake_hold,
            )

            if factor > 0.0:
                pi_demand = self._pi_output(
                    target,
                    indoor,
                    outdoor,
                    now,
                    cfg,
                    freeze_integral=True,
                )
                pi_fake = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - pi_demand))
                brake_temp = self._brake_temp(outdoor, delta_c=brake_delta)
                fake_temp = pi_fake + (brake_temp - pi_fake) * factor
                mode = MODE_BRAKING
            else:
                pi_demand = self._pi_output(target, indoor, outdoor, now, cfg)
                fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - pi_demand))
                mode = MODE_PI

            fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, fake_temp))

            await self._set_state(
                fake_temp,
                mode,
                {
                    **self._base_attrs(
                        indoor,
                        target,
                        outdoor,
                        current_cat,
                        aggressiveness,
                    ),
                    "brake_factor": round(factor, 3),
                    "comfort_floor_c": round(comfort_floor, 2),
                    "ramp_in_minutes": round(ramp_in, 1),
                    "ramp_out_minutes": round(ramp_out, 1),
                },
                now,
            )
            return

        # 5. Pre-brake / preheating before expensive period.
        #
        # These are two distinct behaviours with different trigger conditions:
        #
        # 5a. Pre-brake — pure price signal.
        #     Ramp the brake in during the window before the expensive slot so
        #     the brake is already engaged the moment the slot starts.
        #     Weather data is irrelevant here: if the price is going expensive,
        #     we brake regardless of outdoor temperature.
        #
        # 5b. Preheat-boost — forecast signal.
        #     While prices are still normal and an expensive period is coming,
        #     heat extra so the house has thermal mass to draw on.
        #     Only makes sense when it is actually cold outside — boosting in
        #     warm weather wastes energy without benefit.

        if upcoming:
            minutes_until_expensive = self._minutes_until_expensive(
                categories,
                current_slot,
                interval_minutes,
                now,
            )

            # 5a. Pre-brake: engage ramp when expensive is within ramp_in window.
            if (
                minutes_until_expensive is not None
                and minutes_until_expensive <= ramp_in
            ):
                factor = self._update_brake_ramp(True, now, ramp_in, ramp_out)
                pi_demand = self._pi_output(
                    target,
                    indoor,
                    outdoor,
                    now,
                    cfg,
                    freeze_integral=True,
                )
                pi_fake = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - pi_demand))
                brake_temp = self._brake_temp(outdoor)
                fake_temp = pi_fake + (brake_temp - pi_fake) * factor
                fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, fake_temp))

                await self._set_state(
                    fake_temp,
                    MODE_PREBRAKE,
                    {
                        **self._base_attrs(
                            indoor,
                            target,
                            outdoor,
                            current_cat,
                            aggressiveness,
                        ),
                        "brake_factor": round(factor, 3),
                        "ramp_in_minutes": round(ramp_in, 1),
                        "minutes_until_expensive": round(minutes_until_expensive, 0),
                        "upcoming_expensive": True,
                    },
                    now,
                )
                return

            # 5b. Preheat-boost: heat extra while still cheap, only when cold.
            forecast_cold = self._forecast_is_cold(
                summer_threshold,
                forecast_temps,
                hours=PRICE_LOOKAHEAD_HOURS,
            )
            if forecast_cold and cfg.get("preheat_boost_enabled", True):
                preheat_factor = self._update_preheat_ramp(
                    True,
                    ramp_in=max(ramp_in, 10.0),
                    ramp_out=max(ramp_out, 10.0),
                )

                base_demand = self._pi_output(target, indoor, outdoor, now, cfg)
                boost = PREHEAT_BOOST_C * preheat_factor
                boosted_demand = base_demand + boost
                fake_temp = max(
                    MIN_FAKE_TEMP,
                    min(MAX_FAKE_TEMP, outdoor - boosted_demand),
                )

                await self._set_state(
                    fake_temp,
                    MODE_PREHEAT,
                    {
                        **self._base_attrs(
                            indoor,
                            target,
                            outdoor,
                            current_cat,
                            aggressiveness,
                            boosted_demand,
                        ),
                        "preheat_boost_c": round(boost, 2),
                        "preheat_factor": round(preheat_factor, 3),
                        "brake_factor": 0.0,
                        "minutes_until_expensive": (
                            round(minutes_until_expensive, 0)
                            if minutes_until_expensive
                            else None
                        ),
                        "upcoming_expensive": True,
                    },
                    now,
                )
                return

        # Compute forecast_cold for bridge_short_dip if not already done above.
        # (If upcoming=False the block above was skipped entirely.)
        forecast_cold = self._forecast_is_cold(
            summer_threshold,
            forecast_temps,
            hours=PRICE_LOOKAHEAD_HOURS,
        )
        bridge_short_dip = upcoming and not forecast_cold and self._brake_ramp > 0.0
        if bridge_short_dip:
            log_event("BRIDGE_SHORT_DIP", brake_factor=round(self._brake_ramp, 3))

        # 6. Normal PI control.
        # If the brake is still ramping out (for example after an expensive period
        # or during a bridged short dip), blend fake_temp between pi_fake and
        # brake_temp so the ramp-out is visible in the actual output.
        brake_hold = float(cfg.get("brake_hold_minutes", BRAKE_HOLD_MINUTES))

        self._update_preheat_ramp(
            False,
            ramp_in=max(ramp_in, 10.0),
            ramp_out=max(ramp_out, 10.0),
        )

        pi_demand = self._pi_output(target, indoor, outdoor, now, cfg)
        pi_fake = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - pi_demand))

        factor = self._update_brake_ramp(
            bridge_short_dip,
            now,
            ramp_in,
            ramp_out,
            hold_minutes=brake_hold if self._brake_ramp > 0.0 else 0.0,
        )

        if factor > 0.0:
            brake_temp = self._brake_temp(outdoor)
            fake_temp = pi_fake + (brake_temp - pi_fake) * factor
            fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, fake_temp))
        else:
            fake_temp = pi_fake

        mode = MODE_HOLIDAY if holiday else MODE_PI
        await self._set_state(
            fake_temp,
            mode,
            {
                **self._base_attrs(
                    indoor,
                    target,
                    outdoor,
                    current_cat,
                    aggressiveness,
                    pi_demand,
                ),
                "brake_factor": round(factor, 3),
                "ramp_in_minutes": round(ramp_in, 1),
                "ramp_out_minutes": round(ramp_out, 1),
                "bridge_short_dip": bridge_short_dip,
            },
            now,
        )

    async def _get_prices(
        self,
        cfg: Dict[str, Any],
        now: datetime,
    ) -> Tuple[List[float], List[str], int, int]:
        today_entity_id = cfg.get("electricity_price_entity")
        tomorrow_entity_id = cfg.get("price_tomorrow_entity") or today_entity_id

        if not today_entity_id:
            self._set_price_issue(
                "missing_today_entity",
                "PumpSteer price fetch failed: electricity_price_entity is not configured",
            )
            return [], [], 60, 0

        today_attr = get_attr(self.hass, today_entity_id, "today")
        today_raw_attr = get_attr(self.hass, today_entity_id, "raw_today")
        raw_today = (
            today_attr
            if isinstance(today_attr, list)
            else today_raw_attr if isinstance(today_raw_attr, list) else []
        )

        tomorrow_attr = get_attr(self.hass, tomorrow_entity_id, "tomorrow")
        tomorrow_raw_attr = get_attr(self.hass, tomorrow_entity_id, "raw_tomorrow")
        fallback_tomorrow_attr = get_attr(self.hass, today_entity_id, "tomorrow")
        fallback_tomorrow_raw_attr = get_attr(
            self.hass, today_entity_id, "raw_tomorrow"
        )
        raw_tomorrow = (
            tomorrow_attr
            if isinstance(tomorrow_attr, list)
            else (
                tomorrow_raw_attr
                if isinstance(tomorrow_raw_attr, list)
                else (
                    fallback_tomorrow_attr
                    if isinstance(fallback_tomorrow_attr, list)
                    else (
                        fallback_tomorrow_raw_attr
                        if isinstance(fallback_tomorrow_raw_attr, list)
                        else []
                    )
                )
            )
        )

        prices_raw = [*raw_today, *raw_tomorrow]

        if not prices_raw:
            if (
                today_attr is None
                and today_raw_attr is None
                and tomorrow_attr is None
                and tomorrow_raw_attr is None
                and fallback_tomorrow_attr is None
                and fallback_tomorrow_raw_attr is None
            ):
                self._set_price_issue(
                    "missing_price_attributes",
                    (
                        "PumpSteer price fetch failed: no price list attributes found "
                        f"(today='{today_entity_id}', tomorrow='{tomorrow_entity_id}', "
                        "checked today/raw_today/tomorrow/raw_tomorrow)"
                    ),
                )
            else:
                unsupported_types = []
                for label, value in (
                    ("today", today_attr),
                    ("raw_today", today_raw_attr),
                    ("tomorrow", tomorrow_attr),
                    ("raw_tomorrow", tomorrow_raw_attr),
                    ("fallback_tomorrow", fallback_tomorrow_attr),
                    ("fallback_raw_tomorrow", fallback_tomorrow_raw_attr),
                ):
                    if value is not None and not isinstance(value, list):
                        unsupported_types.append(f"{label}={type(value).__name__}")
                self._set_price_issue(
                    "unsupported_price_format",
                    (
                        "PumpSteer price fetch failed: unsupported price sensor format "
                        f"(today='{today_entity_id}', tomorrow='{tomorrow_entity_id}', "
                        f"details={unsupported_types or ['no list entries']})"
                    ),
                )
            return [], [], 60, 0

        prices: List[float] = []
        invalid_entries = 0
        for item in prices_raw:
            value = PumpSteerSensor._extract_price(item)
            if value is not None and math.isfinite(value):
                prices.append(value)
            else:
                invalid_entries += 1

        if not prices:
            self._set_price_issue(
                "no_usable_prices",
                (
                    "PumpSteer price parsing failed: received raw entries but parsed 0 "
                    f"usable numeric prices (today='{today_entity_id}', "
                    f"tomorrow='{tomorrow_entity_id}', raw_count={len(prices_raw)}, "
                    f"invalid_count={invalid_entries})"
                ),
            )
            return [], [], 60, 0
        self._clear_price_issue(today_entity_id, tomorrow_entity_id)

        if invalid_entries > 0:
            _LOGGER.debug(
                "PumpSteer price parsing skipped %d invalid entries (today='%s', tomorrow='%s')",
                invalid_entries,
                today_entity_id,
                tomorrow_entity_id,
            )

        today_prices: List[float] = []
        for item in raw_today:
            value = PumpSteerSensor._extract_price(item)
            if value is not None and math.isfinite(value):
                today_prices.append(value)

        # Cache price thresholds once per calendar day per entity.
        # Recomputing hourly caused mid-slot reclassification: P80 could shift
        # just enough to flip an ongoing expensive slot to normal, releasing the
        # brake unexpectedly. Daily caching keeps thresholds stable throughout
        # the day; they refresh at midnight when new price data arrives.
        today_date = now.strftime("%Y-%m-%d")
        recalc_thresholds = (
            self._price_thresholds_cached_date is None
            or self._price_thresholds_entity_id != today_entity_id
            or self._price_thresholds_cached_date != today_date
        )

        if recalc_thresholds:
            self._cached_p30, self._cached_p80 = await async_get_price_thresholds(
                today_prices or prices,
            )
            midnight_grace = now.hour == 0 and now.minute < 15
            if today_prices and not midnight_grace:
                self._price_thresholds_cached_date = today_date
                self._price_thresholds_entity_id = today_entity_id
                _LOGGER.debug(
                    "Recomputed price thresholds: p30=%.3f p80=%.3f for entity %s (date=%s)",
                    self._cached_p30,
                    self._cached_p80,
                    today_entity_id,
                    today_date,
                )
                log_event("THRESHOLDS_SET", p30=round(self._cached_p30, 4), p80=round(self._cached_p80, 4), date=today_date)
            else:
                _LOGGER.debug(
                    "Price thresholds not cached yet (today_prices=%s, midnight_grace=%s), "
                    "retry next cycle: p30=%.3f p80=%.3f",
                    bool(today_prices),
                    midnight_grace,
                    self._cached_p30,
                    self._cached_p80,
                )
        self._p30 = self._cached_p30
        self._p80 = self._cached_p80

        if not math.isfinite(self._p30):
            self._p30 = 0.0
        if not math.isfinite(self._p80):
            self._p80 = 0.0

        categories = classify_price_list(prices, self._p30, self._p80)
        interval_source = raw_today if raw_today else prices_raw
        interval_minutes = detect_price_interval_minutes(interval_source)
        categories = filter_short_peaks(
            categories,
            interval_minutes,
            PEAK_FILTER_MIN_DURATION_MINUTES,
        )
        current_slot = compute_price_slot_index(now, interval_minutes, len(prices))

        return prices, categories, interval_minutes, current_slot

    @staticmethod
    def _extract_price(item: Any) -> Optional[float]:
        if item is None:
            return None

        if isinstance(item, dict):
            for key in ("value", "price"):
                if key in item:
                    return PumpSteerSensor._extract_price(item[key])
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

    async def _set_state(
        self,
        fake_temp: float,
        mode: str,
        extra: Dict[str, Any],
        now: datetime,
    ) -> None:
        if self._safe_mode_warned and mode != MODE_SAFE:
            _LOGGER.info(
                "PumpSteer exited SAFE MODE and returned to normal control (mode=%s)",
                mode,
            )
            log_event("SAFE_MODE_EXIT", new_mode=mode)
            self._safe_mode_warned = False
        self._state = round(fake_temp, 1)
        log_mode_change(
            old_mode=self._prev_mode,
            new_mode=mode,
            fake_temp=fake_temp,
            indoor=extra.get("indoor_temperature"),
            outdoor=extra.get("outdoor_temperature"),
            price_cat=extra.get("price_category"),
            p30=getattr(self, "_p30", None),
            p80=getattr(self, "_p80", None),
            brake_factor=extra.get("brake_factor"),
            ramp_in=extra.get("ramp_in_minutes"),
            comfort_floor=extra.get("comfort_floor_c"),
        )
        self._prev_mode = mode
        self._attributes = {
            "mode": mode,
            "fake_outdoor_temperature": self._state,
            "status": "ok",
            "last_updated": now.isoformat(),
            **extra,
        }

        self._ohmigo_last_push = await async_push_ohmigo(
            self.hass,
            self._config_entry,
            fake_temp,
            self._ohmigo_last_push,
        )


class ThermalOutlookSensor(SensorEntity):
    """Exposes ThermalOutlook as a HA sensor for visualization and debugging."""

    _attr_has_entity_name = True
    _attr_name = "Thermal Outlook"
    _attr_icon = "mdi:weather-partly-cloudy"
    _attr_should_poll = True

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.hass = hass
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_thermal_outlook"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="PumpSteer",
            manufacturer="PumpSteer",
            model="Heat Pump Controller",
            sw_version=SW_VERSION,
        )
        self._outlook: Optional[Any] = None

    @property
    def state(self) -> str:
        if self._outlook is None:
            return "unavailable"
        if self._outlook.preheat_worthwhile:
            return "preheat"
        if self._outlook.precool_risk:
            return "precool_risk"
        if self._outlook.warming_trend:
            return "warming"
        return "neutral"

    @property
    def extra_state_attributes(self) -> dict:
        if self._outlook is None:
            return {}
        o = self._outlook
        return {
            "night_min_temp": o.night_min_temp,
            "day_max_temp": o.day_max_temp,
            "hours_below_threshold": o.hours_below_threshold,
            "effective_temp_now": (
                round(o.effective_temp_now, 1) if o.effective_temp_now is not None else None
            ),
            "warming_trend": o.warming_trend,
            "cooling_trend": o.cooling_trend,
            "precool_risk": o.precool_risk,
            "preheat_worthwhile": o.preheat_worthwhile,
            "preheat_strength": round(o.preheat_strength, 2),
        }

    async def async_update(self) -> None:
        """Fetch forecast and compute ThermalOutlook."""
        from .forecast import async_build_forecast, analyze_thermal_outlook

        cfg = {**self._config_entry.data, **self._config_entry.options}
        weather_entity = cfg.get("weather_entity")
        price_entity = cfg.get("electricity_price_entity")
        summer_threshold = float(cfg.get("summer_threshold", DEFAULT_SUMMER_THRESHOLD))

        if not weather_entity or not price_entity:
            return
        try:
            points = await async_build_forecast(
                self.hass,
                price_entity_id=price_entity,
                weather_entity_id=weather_entity,
                horizon_hours=24,
            )
            self._outlook = analyze_thermal_outlook(
                points,
                summer_threshold=summer_threshold,
                now_hour=dt_util.now().hour,
            )
        except Exception as err:
            _LOGGER.debug("ThermalOutlookSensor update failed: %s", err)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    from .pump_log import setup_pump_log
    await hass.async_add_executor_job(setup_pump_log)
    sensor = PumpSteerSensor(hass, config_entry)
    outlook_sensor = ThermalOutlookSensor(hass, config_entry)
    async_add_entities([sensor, outlook_sensor], update_before_add=False)
