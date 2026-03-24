import logging
import math
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .control import PIController
from .holiday import async_update_holiday
from .electricity_price import (
    async_get_price_thresholds,
    classify_price_list,
    filter_short_peaks,
    price_category_index,
    PRICE_NORMAL,
    PRICE_EXPENSIVE,
)
from .settings import (
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
    PRECOOL_LOOKAHEAD,
    PRECOOL_MARGIN,
    PID_KP,
    PID_KI,
    PID_KD,
    PID_INTEGRAL_CLAMP,
    PID_OUTPUT_CLAMP,
    COMFORT_FLOOR_BY_AGGRESSIVENESS,
    RAMP_SCALE,
    RAMP_MIN_MINUTES,
    RAMP_MAX_MINUTES,
    PREHEAT_BOOST_C,
    PEAK_FILTER_MIN_DURATION_MINUTES,
    PRICE_LOOKAHEAD_HOURS,
    DEFAULT_SUMMER_THRESHOLD,
    DEFAULT_AGGRESSIVENESS,
    DEFAULT_HOUSE_INERTIA,
    DEFAULT_TARGET_TEMP,
    HOLIDAY_TEMP,
    BRAKE_DELTA_C,
    BRAKE_HOLD_MINUTES,
    PREHEAT_ON_MISSING_FORECAST,
)
from .utils import (
    safe_float,
    get_state,
    get_attr,
    get_version,
    detect_price_interval_minutes,
    compute_price_slot_index,
    safe_parse_temperature_forecast,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"
SW_VERSION = get_version()

# Hardcoded HA entity IDs created by the package.
PACKAGE_ENTITIES = {
    "target_temp": "input_number.indoor_target_temperature",
    "summer_threshold": "input_number.pumpsteer_summer_threshold",
    "aggressiveness": "input_number.pumpsteer_aggressiveness",
    "house_inertia": "input_number.pumpsteer_house_inertia",
    "forecast_temps": "input_text.hourly_forecast_temperatures",
}

# Operating modes.
MODE_SUMMER = "summer_mode"
MODE_PRECOOL = "precool"
MODE_PREHEAT = "preheating"
MODE_BRAKING = "braking"
MODE_PI = "normal"
MODE_HOLIDAY = "holiday"
MODE_ERROR = "error"
MODE_SAFE = "safe_mode"


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

        self._pi = PIController()

        self._brake_ramp: float = 0.0
        self._brake_last_t: Optional[datetime] = None
        self._brake_last_expensive_t: Optional[datetime] = None
        self._ramp_in_minutes: float = 15.0
        self._ramp_out_minutes: float = 15.0

        self._last_price_categories: List[str] = []
        self._p30: float = 0.0
        self._p80: float = 0.0

        # Cache price thresholds to avoid recorder/history lookups on every poll.
        # Recompute at most once per hour, after restart, or if the price entity changes.
        self._price_thresholds_cached_at: Optional[datetime] = None
        self._price_thresholds_entity_id: Optional[str] = None
        self._cached_p30: float = 0.0
        self._cached_p80: float = 0.0

        # Track previous aggressiveness to detect transition into aggressiveness=0.
        # The PI reset should happen once on entry, not on every cycle.
        self._prev_aggressiveness: Optional[int] = None

        # Store the remove callback returned by add_update_listener so it can
        # be cleaned up on unload.
        self._remove_update_listener = None

        self._attr_unique_id = config_entry.entry_id
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

    async def async_added_to_hass(self) -> None:
        """Restore last state and register options update listener."""
        await super().async_added_to_hass()

        self._remove_update_listener = self._config_entry.add_update_listener(
            self.async_options_update_listener
        )

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
                _LOGGER.debug(
                    "PumpSteer restored state %.1f°C (mode=%s) after restart",
                    self._state,
                    self._attributes.get("mode", "unknown"),
                )

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

    def _cfg(self) -> Dict[str, Any]:
        return {**self._config_entry.data, **self._config_entry.options}

    def _read_entity(
        self,
        entity_id: str,
        default: Optional[float] = None,
    ) -> Optional[float]:
        return safe_float(get_state(self.hass, entity_id)) if entity_id else default

    def _aggressiveness(self, cfg: Dict[str, Any]) -> int:
        raw = (
            cfg.get("aggressiveness")
            or self._read_entity(PACKAGE_ENTITIES["aggressiveness"])
            or DEFAULT_AGGRESSIVENESS
        )
        return max(0, min(5, int(round(float(raw)))))

    def _house_inertia(self, cfg: Dict[str, Any]) -> float:
        raw = (
            cfg.get("house_inertia")
            or self._read_entity(PACKAGE_ENTITIES["house_inertia"])
            or DEFAULT_HOUSE_INERTIA
        )
        return max(0.5, min(10.0, float(raw)))

    def _comfort_floor(self, target: float, aggressiveness: int) -> float:
        drop = COMFORT_FLOOR_BY_AGGRESSIVENESS[aggressiveness]
        return target - drop

    def _brake_temp(self, outdoor: float, delta_c: Optional[float] = None) -> float:
        delta = delta_c if delta_c is not None else BRAKE_DELTA_C
        return min(max(outdoor + delta, MIN_FAKE_TEMP), MAX_FAKE_TEMP)

    def _compute_ramp_minutes(
        self,
        current_cat: str,
        next_cat: str,
        house_inertia: float,
    ) -> float:
        current_index = price_category_index(current_cat)
        next_index = price_category_index(next_cat)
        jump = max(0, next_index - current_index)
        ramp = jump * house_inertia * RAMP_SCALE
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

    def _forecast_temps(self) -> Optional[List[float]]:
        raw = get_state(self.hass, PACKAGE_ENTITIES["forecast_temps"])
        if not raw:
            return None
        return safe_parse_temperature_forecast(raw, max_hours=PRECOOL_LOOKAHEAD)

    def _should_precool(self, summer_threshold: float) -> bool:
        temps = self._forecast_temps()
        if not temps:
            return False
        return any(temp >= summer_threshold + PRECOOL_MARGIN for temp in temps)

    def _forecast_is_cold(self, summer_threshold: float, hours: int = 6) -> bool:
        temps = self._forecast_temps()
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
        """
        Enter safe mode.

        Safe mode passes through the real outdoor temperature and resets PI
        and brake state to avoid drift.
        """
        _LOGGER.warning(
            "PumpSteer SAFE MODE: %s — optimization paused, sending real outdoor temp",
            reason,
        )

        self._pi.reset(now)
        self._brake_ramp = 0.0
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
        """Update brake ramp factor with optional hold time."""
        if self._brake_last_t is None:
            dt_seconds = 60.0
        else:
            dt_seconds = max((now - self._brake_last_t).total_seconds(), 1.0)

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
        target = (
            self._read_entity(PACKAGE_ENTITIES["target_temp"])
            or DEFAULT_TARGET_TEMP
        )
        summer_threshold = (
            self._read_entity(PACKAGE_ENTITIES["summer_threshold"])
            or DEFAULT_SUMMER_THRESHOLD
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

        holiday = await async_update_holiday(self.hass)
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
        next_cat = self._next_period_category(categories, current_slot, interval_minutes)

        if next_cat:
            ramp_in = self._compute_ramp_minutes(
                current_cat,
                next_cat,
                house_inertia,
            )
        else:
            ramp_in = 15.0

        ramp_out = max(RAMP_MIN_MINUTES, ramp_in * 0.5)

        lookahead_slots = max(
            1,
            math.ceil((PRICE_LOOKAHEAD_HOURS * 60) / max(interval_minutes, 1)),
        )

        comfort_floor = self._comfort_floor(target, aggressiveness)

        # 1. Summer mode.
        if outdoor >= summer_threshold:
            self._pi.reset(now)
            self._brake_ramp = 0.0
            self._brake_last_t = None
            self._prev_aggressiveness = None

            fake_temp = outdoor
            self._set_state(
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
        if self._should_precool(summer_threshold):
            brake_temp = self._brake_temp(outdoor)
            factor = self._update_brake_ramp(
                True,
                now,
                ramp_in=10.0,
                ramp_out=20.0,
            )
            fake_temp = outdoor + (brake_temp - outdoor) * factor
            fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, fake_temp))

            self._set_state(
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
                self._brake_last_t = None

            self._prev_aggressiveness = 0

            demand = self._pi_output(target, indoor, outdoor, now, cfg)
            fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - demand))

            self._set_state(
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
                brake_requested = False
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
                # Keep PI ticking even at near/full brake so dt does not jump
                # when leaving expensive mode. This avoids abrupt integral steps.
                mode = MODE_BRAKING
            else:
                pi_demand = self._pi_output(target, indoor, outdoor, now, cfg)
                fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - pi_demand))
                mode = MODE_PI

            fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, fake_temp))

            self._set_state(
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

        # 5. Preheating / pre-brake before expensive period.
        upcoming = self._upcoming_expensive(categories, current_slot, lookahead_slots)
        forecast_cold = self._forecast_is_cold(
            summer_threshold,
            hours=PRICE_LOOKAHEAD_HOURS,
        )

        if upcoming and forecast_cold:
            minutes_until_expensive = self._minutes_until_expensive(
                categories,
                current_slot,
                interval_minutes,
                now,
            )

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

                self._set_state(
                    fake_temp,
                    MODE_PREHEAT,
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

            base_demand = self._pi_output(target, indoor, outdoor, now, cfg)
            boosted_demand = base_demand + PREHEAT_BOOST_C
            fake_temp = max(
                MIN_FAKE_TEMP,
                min(MAX_FAKE_TEMP, outdoor - boosted_demand),
            )

            self._update_brake_ramp(False, now, ramp_in, ramp_out)

            self._set_state(
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
                    "preheat_boost_c": PREHEAT_BOOST_C,
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

        # 6. Normal PI control.
        demand = self._pi_output(target, indoor, outdoor, now, cfg)
        fake_temp = max(MIN_FAKE_TEMP, min(MAX_FAKE_TEMP, outdoor - demand))
        self._update_brake_ramp(False, now, ramp_in, ramp_out)

        mode = MODE_HOLIDAY if holiday else MODE_PI
        self._set_state(
            fake_temp,
            mode,
            {
                **self._base_attrs(
                    indoor,
                    target,
                    outdoor,
                    current_cat,
                    aggressiveness,
                    demand,
                ),
            },
            now,
        )

    async def _get_prices(
        self,
        cfg: Dict[str, Any],
        now: datetime,
    ) -> Tuple[List[float], List[str], int, int]:
        """
        Read price data from configured entities.

        Backward compatibility:
        - Older setups may expose both today and tomorrow on the same entity
          using raw_today/raw_tomorrow or today/tomorrow.
        - Newer setups typically expose:
            electricity_price_entity -> current price state + attribute "today"
            price_tomorrow_entity    -> attribute "tomorrow"
        """
        today_entity_id = cfg.get("electricity_price_entity")
        tomorrow_entity_id = cfg.get("price_tomorrow_entity") or today_entity_id

        if not today_entity_id:
            return [], [], 60, 0

        raw_today = (
            get_attr(self.hass, today_entity_id, "today")
            or get_attr(self.hass, today_entity_id, "raw_today")
            or []
        )

        raw_tomorrow = (
            get_attr(self.hass, tomorrow_entity_id, "tomorrow")
            or get_attr(self.hass, tomorrow_entity_id, "raw_tomorrow")
            or get_attr(self.hass, today_entity_id, "tomorrow")
            or get_attr(self.hass, today_entity_id, "raw_tomorrow")
            or []
        )

        prices_raw = [*raw_today, *raw_tomorrow]

        if not prices_raw:
            _LOGGER.warning(
                "No price data from today entity '%s' and tomorrow entity '%s'",
                today_entity_id,
                tomorrow_entity_id,
            )
            return [], [], 60, 0

        prices: List[float] = []
        for item in prices_raw:
            value = PumpSteerSensor._extract_price(item)
            if value is not None and math.isfinite(value):
                prices.append(value)

        if not prices:
            return [], [], 60, 0

        today_prices: List[float] = []
        for item in raw_today:
            value = PumpSteerSensor._extract_price(item)
            if value is not None and math.isfinite(value):
                today_prices.append(value)

        recalc_thresholds = False

        if self._price_thresholds_cached_at is None:
            recalc_thresholds = True
        elif self._price_thresholds_entity_id != today_entity_id:
            recalc_thresholds = True
        else:
            cache_age_seconds = (
                now - self._price_thresholds_cached_at
            ).total_seconds()
            if cache_age_seconds >= 3600:
                recalc_thresholds = True

        if recalc_thresholds:
            self._cached_p30, self._cached_p80 = await async_get_price_thresholds(
                self.hass,
                today_entity_id,
                today_prices or prices,
            )
            self._price_thresholds_cached_at = now
            self._price_thresholds_entity_id = today_entity_id
            _LOGGER.debug(
                "Recomputed price thresholds: p30=%.3f p80=%.3f for entity %s",
                self._cached_p30,
                self._cached_p80,
                today_entity_id,
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
        """Extract a numeric price value from supported input formats."""
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

    def _set_state(
        self,
        fake_temp: float,
        mode: str,
        extra: Dict[str, Any],
        now: datetime,
    ) -> None:
        """Store final state and attributes."""
        self._state = round(fake_temp, 1)
        self._attributes = {
            "mode": mode,
            "fake_outdoor_temperature": self._state,
            "status": "ok",
            "last_updated": now.isoformat(),
            **extra,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PumpSteer sensor from a config entry."""
    sensor = PumpSteerSensor(hass, config_entry)
    async_add_entities([sensor], update_before_add=True)
