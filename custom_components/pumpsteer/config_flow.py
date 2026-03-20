import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.helpers.selector import selector

from .options_flow import PumpSteerOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

# Hardcoded entities that are expected to exist in the package setup
HARDCODED_ENTITIES = {
    "target_temp_entity": "input_number.indoor_target_temperature",
    "summer_threshold_entity": "input_number.pumpsteer_summer_threshold",
    "auto_tune_inertia_entity": "input_boolean.autotune_inertia",
    "hourly_forecast_temperatures_entity": "input_text.hourly_forecast_temperatures",
}


class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PumpSteer."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            combined_data = {**user_input, **HARDCODED_ENTITIES}
            errors = await self._validate_entities(combined_data)

            if not errors:
                return self.async_create_entry(
                    title="PumpSteer",
                    data=combined_data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("indoor_temp_entity"): selector(
                        {"entity": {"domain": "sensor", "device_class": "temperature"}}
                    ),
                    vol.Required("real_outdoor_entity"): selector(
                        {"entity": {"domain": "sensor", "device_class": "temperature"}}
                    ),
                    vol.Required("electricity_price_entity"): selector(
                        {"entity": {"domain": "sensor"}}
                    ),
                }
            ),
            errors=errors,
        )

    async def _validate_entities(self, user_input):
        """Validate required entities."""
        errors = {}

        user_selected_entities = {
            "indoor_temp_entity": "Indoor temperature sensor",
            "real_outdoor_entity": "Outdoor temperature sensor",
            "electricity_price_entity": "Electricity price sensor",
        }

        hardcoded_entities = {
            "hourly_forecast_temperatures_entity": "Temperature forecast input_text",
            "target_temp_entity": "Target temperature input_number",
            "summer_threshold_entity": "Summer threshold input_number",
            "auto_tune_inertia_entity": "Autotune inertia boolean",
        }

        # User-selected entities must exist and be available during setup
        for field, description in user_selected_entities.items():
            entity_id = user_input.get(field)

            if not entity_id:
                errors[field] = "required"
                continue

            if not self._entity_exists(entity_id):
                _LOGGER.error(
                    "Required entity not found: %s (%s)",
                    entity_id,
                    description,
                )
                errors[field] = "entity_not_found"
                continue

            if not self._entity_available(entity_id):
                _LOGGER.error(
                    "Required entity is unavailable during setup: %s (%s)",
                    entity_id,
                    description,
                )
                errors[field] = "entity_unavailable"

        # Hardcoded entities should exist, but only warn if missing or unavailable
        for field, description in hardcoded_entities.items():
            entity_id = user_input.get(field)

            if not entity_id:
                continue

            if not self._entity_exists(entity_id):
                _LOGGER.warning(
                    "Hardcoded entity not found: %s (%s) - This should be created by the package",
                    entity_id,
                    description,
                )
            elif not self._entity_available(entity_id):
                _LOGGER.warning(
                    "Hardcoded entity unavailable: %s (%s) - Check package configuration",
                    entity_id,
                    description,
                )

        return errors

    def _entity_exists(self, entity_id: str) -> bool:
        """Return True if the entity exists."""
        return self.hass.states.get(entity_id) is not None

    def _entity_available(self, entity_id: str) -> bool:
        """Return True if the entity exists and has a valid state."""
        entity = self.hass.states.get(entity_id)
        if entity is None:
            return False

        return entity.state not in {
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            "unavailable",
            "unknown",
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return PumpSteerOptionsFlowHandler(config_entry)
