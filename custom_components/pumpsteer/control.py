"""
PumpSteer control module.

Contains:
  - PIResult / PIController  — discrete-time PI controller used by sensor.py
  - PumpSteerConfigFlow      — Home Assistant config flow for integration setup
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.helpers.selector import selector

from .options_flow import PumpSteerOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)
DOMAIN = "pumpsteer"

HARDCODED_ENTITIES = {
    "target_temp_entity":      "input_number.indoor_target_temperature",
    "summer_threshold_entity": "input_number.pumpsteer_summer_threshold",
    "aggressiveness_entity":   "input_number.pumpsteer_aggressiveness",
    "house_inertia_entity":    "input_number.pumpsteer_house_inertia",
    "forecast_entity":         "input_text.hourly_forecast_temperatures",
    "holiday_entity":          "input_boolean.pumpsteer_holiday_mode",
}


# ── PI Controller ─────────────────────────────────────────────────────────────

@dataclass
class PIResult:
    """Result from one PI controller compute step."""
    offset: float
    p_term: float
    i_term: float
    error: float


class PIController:
    """
    Discrete-time PI controller for PumpSteer.
    offset < 0 → heat more (sensor.py negates to get positive demand).
    Anti-windup via integral clamp.
    brake_behavior='freeze' keeps integral constant while braking.
    brake_behavior='decay' slowly reduces it.
    """

    def __init__(self) -> None:
        self._integral: float = 0.0
        self._last_time: Optional[datetime] = None
        self._last_error: float = 0.0

    def reset(self, now: datetime) -> None:
        """Reset controller state (on mode switch or safe mode entry)."""
        self._integral = 0.0
        self._last_time = now
        self._last_error = 0.0
        _LOGGER.debug("PIController reset")

    def compute(
        self,
        target_temp: float,
        indoor_temp: float,
        outdoor_temp: float,
        aggressiveness: float,
        update_time: datetime,
        braking_active: bool = False,
        kp: float = 8.0,
        ki: float = 0.05,
        kd: float = 0.0,
        feedforward_bias: float = 0.0,
        integral_clamp: float = 10.0,
        output_clamp: float = 20.0,
        min_fake_temp: float = -25.0,
        max_fake_temp: float = 25.0,
        brake_behavior: str = "freeze",
        decay_per_minute_on_brake: float = 0.98,
    ) -> PIResult:
        if self._last_time is None:
            dt_minutes = 1.0
        else:
            dt_seconds = (update_time - self._last_time).total_seconds()
            dt_minutes = max(dt_seconds / 60.0, 0.01)
        self._last_time = update_time

        error = target_temp - indoor_temp
        p_term = kp * error

        if braking_active:
            if brake_behavior == "decay":
                self._integral *= (decay_per_minute_on_brake ** dt_minutes)
        else:
            self._integral += ki * error * dt_minutes
            self._integral = max(-integral_clamp, min(integral_clamp, self._integral))
        i_term = self._integral

        d_term = 0.0
        if kd > 0 and dt_minutes > 0:
            d_term = kd * (error - self._last_error) / dt_minutes
        self._last_error = error

        raw_output = -(p_term + i_term + d_term + feedforward_bias)
        clamped = max(-output_clamp, min(output_clamp, raw_output))

        _LOGGER.debug(
            "PI: error=%.2f P=%.2f I=%.2f → offset=%.2f (dt=%.1f min, braking=%s)",
            error, p_term, i_term, clamped, dt_minutes, braking_active,
        )
        return PIResult(offset=clamped, p_term=p_term, i_term=i_term, error=error)


# ── Config Flow ───────────────────────────────────────────────────────────────

class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PumpSteer."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            combined = {**user_input, **HARDCODED_ENTITIES}
            errors = self._validate_entities(user_input)
            if not errors:
                return self.async_create_entry(title="PumpSteer", data=combined)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("indoor_temp_entity"): selector(
                    {"entity": {"domain": "sensor", "device_class": "temperature"}}
                ),
                vol.Required("real_outdoor_entity"): selector(
                    {"entity": {"domain": "sensor", "device_class": "temperature"}}
                ),
                vol.Required("electricity_price_entity"): selector(
                    {"entity": {"domain": "sensor"}}
                ),
            }),
            errors=errors,
        )

    def _validate_entities(self, user_input: dict) -> dict:
        errors = {}
        for field in ("indoor_temp_entity", "real_outdoor_entity", "electricity_price_entity"):
            entity_id = user_input.get(field)
            if not entity_id:
                errors[field] = "required"
                continue
            if not self._entity_exists(entity_id):
                errors[field] = "entity_not_found"
                continue
            if not self._entity_available(entity_id):
                errors[field] = "entity_unavailable"
        for key, entity_id in HARDCODED_ENTITIES.items():
            if not self._entity_exists(entity_id):
                _LOGGER.warning(
                    "Package entity not found: %s — make sure pumpsteer.yaml is loaded",
                    entity_id,
                )
        return errors

    def _entity_exists(self, entity_id: str) -> bool:
        return self.hass.states.get(entity_id) is not None

    def _entity_available(self, entity_id: str) -> bool:
        entity = self.hass.states.get(entity_id)
        if not entity:
            return False
        return entity.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN, "unavailable", "unknown"}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PumpSteerOptionsFlowHandler()
