import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.selector import selector

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

HARDCODED_ENTITIES = {
    "target_temp_entity":       "input_number.indoor_target_temperature",
    "summer_threshold_entity":  "input_number.pumpsteer_summer_threshold",
    "aggressiveness_entity":    "input_number.pumpsteer_aggressiveness",
    "house_inertia_entity":     "input_number.pumpsteer_house_inertia",
    "forecast_entity":          "input_text.hourly_forecast_temperatures",
    "holiday_entity":           "input_boolean.pumpsteer_holiday_mode",
}


class PumpSteerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for PumpSteer."""

    async def async_step_init(self, user_input=None):
        errors = {}
        entry = self.config_entry
        current = {**entry.data, **entry.options}

        if user_input is not None:
            try:
                errors = self._validate(user_input)
                if not errors:
                    return self.async_create_entry(
                        title="",
                        data={**user_input, **HARDCODED_ENTITIES},
                    )
            except Exception as err:
                _LOGGER.exception("Options save failed: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    "indoor_temp_entity",
                    default=current.get("indoor_temp_entity"),
                ): selector({"entity": {"domain": "sensor", "device_class": "temperature"}}),

                vol.Required(
                    "real_outdoor_entity",
                    default=current.get("real_outdoor_entity"),
                ): selector({"entity": {"domain": "sensor", "device_class": "temperature"}}),

                vol.Required(
                    "electricity_price_entity",
                    default=current.get("electricity_price_entity"),
                ): selector({"entity": {"domain": "sensor"}}),

                # Advanced PI tuning — hidden from most users, kept for power users
                vol.Optional(
                    "pid_kp",
                    default=current.get("pid_kp", 2.4),
                ): selector({"number": {"min": 0.0, "max": 20.0, "step": 0.1, "mode": "box"}}),

                vol.Optional(
                    "pid_ki",
                    default=current.get("pid_ki", 0.035),
                ): selector({"number": {"min": 0.0, "max": 2.0, "step": 0.001, "mode": "box"}}),

                vol.Optional(
                    "pid_kd",
                    default=current.get("pid_kd", 0.0),
                ): selector({"number": {"min": 0.0, "max": 2.0, "step": 0.001, "mode": "box"}}),

                vol.Optional(
                    "pid_integral_clamp",
                    default=current.get("pid_integral_clamp", 6.0),
                ): selector({"number": {"min": 0.0, "max": 30.0, "step": 0.5, "mode": "box"}}),

                vol.Optional(
                    "pid_output_clamp",
                    default=current.get("pid_output_clamp", 20.0),
                ): selector({"number": {"min": 0.0, "max": 30.0, "step": 0.5, "mode": "box"}}),

                vol.Optional(
                    "brake_delta_c",
                    default=current.get("brake_delta_c", 12.0),
                ): selector({"number": {"min": 5.0, "max": 25.0, "step": 1.0, "mode": "slider"}}),

                vol.Optional(
                    "brake_hold_minutes",
                    default=current.get("brake_hold_minutes", 30.0),
                ): selector({"number": {"min": 0.0, "max": 120.0, "step": 15.0, "mode": "slider"}}),
            }),
            errors=errors,
        )

    def _validate(self, user_input: dict) -> dict:
        errors = {}
        for field in ("indoor_temp_entity", "real_outdoor_entity", "electricity_price_entity"):
            entity_id = user_input.get(field)
            if not entity_id:
                errors[field] = "required"
            elif not self._entity_exists(entity_id):
                errors[field] = "entity_not_found"
        return errors

    def _entity_exists(self, entity_id: str) -> bool:
        return self.hass.states.get(entity_id) is not None
