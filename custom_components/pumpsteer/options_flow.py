import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.selector import selector

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

HARDCODED_ENTITIES = {
    "target_temp_entity": "input_number.indoor_target_temperature",
    "summer_threshold_entity": "input_number.pumpsteer_summer_threshold",
    "auto_tune_inertia_entity": "input_boolean.autotune_inertia",
    "hourly_forecast_temperatures_entity": "input_text.hourly_forecast_temperatures",
}


class PumpSteerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for PumpSteer."""

    async def async_step_init(self, user_input=None):
        """Manage the options flow."""
        errors = {}

        entry = self.config_entry
        current_data = {**entry.data, **entry.options}

        if user_input is not None:
            try:
                entity_errors = self._validate_entities(user_input)
                range_errors = self._validate_numeric_ranges(user_input)
                errors = {**entity_errors, **range_errors}

                if not errors:
                    combined_data = {**user_input, **HARDCODED_ENTITIES}
                    return self.async_create_entry(title="", data=combined_data)

            except Exception as err:
                _LOGGER.exception("Options flow save failed: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "indoor_temp_entity",
                        default=current_data.get("indoor_temp_entity"),
                    ): selector(
                        {"entity": {"domain": "sensor", "device_class": "temperature"}}
                    ),
                    vol.Required(
                        "real_outdoor_entity",
                        default=current_data.get("real_outdoor_entity"),
                    ): selector(
                        {"entity": {"domain": "sensor", "device_class": "temperature"}}
                    ),
                    vol.Required(
                        "electricity_price_entity",
                        default=current_data.get(
                            "electricity_price_entity",
                            "sensor.elpris_today",
                        ),
                    ): selector({"entity": {"domain": "sensor"}}),
                    vol.Required(
                        "price_tomorrow_entity",
                        default=current_data.get(
                            "price_tomorrow_entity",
                            "sensor.elpris_tomorrow",
                        ),
                    ): selector({"entity": {"domain": "sensor"}}),
                    vol.Optional(
                        "pid_kp",
                        default=current_data.get("pid_kp", 2.4),
                    ): selector(
                        {"number": {"min": 0.0, "max": 20.0, "step": 0.1, "mode": "box"}}
                    ),
                    vol.Optional(
                        "pid_ki",
                        default=current_data.get("pid_ki", 0.035),
                    ): selector(
                        {"number": {"min": 0.0, "max": 2.0, "step": 0.001, "mode": "box"}}
                    ),
                    vol.Optional(
                        "pid_kd",
                        default=current_data.get("pid_kd", 0.0),
                    ): selector(
                        {"number": {"min": 0.0, "max": 2.0, "step": 0.001, "mode": "box"}}
                    ),
                    vol.Optional(
                        "pid_integral_clamp",
                        default=current_data.get("pid_integral_clamp", 6.0),
                    ): selector(
                        {"number": {"min": 0.0, "max": 30.0, "step": 0.1, "mode": "box"}}
                    ),
                    vol.Optional(
                        "pid_output_clamp",
                        default=current_data.get("pid_output_clamp", 12.0),
                    ): selector(
                        {"number": {"min": 0.0, "max": 30.0, "step": 0.1, "mode": "box"}}
                    ),
                    vol.Optional(
                        "pid_integrator_on_brake",
                        default=current_data.get("pid_integrator_on_brake", "freeze"),
                    ): selector(
                        {"select": {"options": ["freeze", "decay", "reset"], "mode": "dropdown"}}
                    ),
                    vol.Optional(
                        "pid_decay_per_minute_on_brake",
                        default=current_data.get("pid_decay_per_minute_on_brake", 0.98),
                    ): selector(
                        {"number": {"min": 0.5, "max": 1.0, "step": 0.01, "mode": "box"}}
                    ),
                    vol.Optional(
                        "pi_price_feedforward_gain",
                        default=current_data.get("pi_price_feedforward_gain", 1.0),
                    ): selector(
                        {"number": {"min": 0.0, "max": 10.0, "step": 0.1, "mode": "box"}}
                    ),
                    vol.Optional(
                        "pi_forecast_feedforward_gain",
                        default=current_data.get("pi_forecast_feedforward_gain", 1.0),
                    ): selector(
                        {"number": {"min": 0.0, "max": 10.0, "step": 0.1, "mode": "box"}}
                    ),
                    vol.Optional(
                        "brake_ramp_in_minutes",
                        default=current_data.get("brake_ramp_in_minutes", 15.0),
                    ): selector(
                        {"number": {"min": 0.1, "max": 120.0, "step": 0.1, "mode": "box"}}
                    ),
                    vol.Optional(
                        "brake_ramp_out_minutes",
                        default=current_data.get("brake_ramp_out_minutes", 15.0),
                    ): selector(
                        {"number": {"min": 0.1, "max": 120.0, "step": 0.1, "mode": "box"}}
                    ),
                    vol.Optional(
                        "min_brake_strength",
                        default=current_data.get("min_brake_strength", 0.0),
                    ): selector(
                        {"number": {"min": 0.0, "max": 1.0, "step": 0.01, "mode": "box"}}
                    ),
                    vol.Optional(
                        "max_brake_strength",
                        default=current_data.get("max_brake_strength", 1.0),
                    ): selector(
                        {"number": {"min": 0.0, "max": 1.0, "step": 0.01, "mode": "box"}}
                    ),
                    # FIX 4: experimental_ml_enabled removed — ML is out of scope
                    # for 2.0.0 per ARCHITECTURE.md and ROADMAP.md.
                }
            ),
            errors=errors,
        )

    def _validate_entities(self, user_input):
        """Validate that entities exist and are available."""
        errors = {}

        user_configurable_entities = {
            "indoor_temp_entity": "Indoor temperature sensor",
            "real_outdoor_entity": "Outdoor temperature sensor",
            "electricity_price_entity": "Electricity price sensor",
            "price_tomorrow_entity": "Tomorrow electricity price sensor",
        }

        for field, description in user_configurable_entities.items():
            entity_id = user_input.get(field)
            if not entity_id:
                errors[field] = "required"
                continue

            if not self._entity_exists(entity_id):
                _LOGGER.warning("%s not found: %s", description, entity_id)
                errors[field] = "entity_not_found"
                continue

            if not self._entity_available(entity_id):
                _LOGGER.warning("%s unavailable: %s", description, entity_id)
                errors[field] = "entity_unavailable"

        return errors

    def _validate_numeric_ranges(self, user_input):
        """Validate logical numeric relationships."""
        errors = {}

        try:
            min_brake = float(user_input.get("min_brake_strength", 0.0))
            max_brake = float(user_input.get("max_brake_strength", 1.0))
        except (TypeError, ValueError):
            return {"base": "invalid_numeric"}

        if min_brake > max_brake:
            errors["min_brake_strength"] = "invalid_range"
            errors["max_brake_strength"] = "invalid_range"

        return errors

    def _entity_exists(self, entity_id: str) -> bool:
        """Return True if the entity exists."""
        return self.hass.states.get(entity_id) is not None

    def _entity_available(self, entity_id: str) -> bool:
        """Return True if the entity is available."""
        entity = self.hass.states.get(entity_id)
        if not entity:
            return False

        return entity.state not in {
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            "unavailable",
            "unknown",
        }
