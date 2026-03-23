import logging
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


class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PumpSteer."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
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

        # Warn (but don't block) if package entities are missing
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
        """Return the options flow handler."""
        return PumpSteerOptionsFlowHandler()
