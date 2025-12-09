import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import selector
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

# Import your OptionsFlowHandler here
from .options_flow import PumpSteerOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

# Hardcoded entities that are always present in the package file
HARDCODED_ENTITIES = {
    "target_temp_entity": "input_number.indoor_target_temperature",
    "summer_threshold_entity": "input_number.pumpsteer_summer_threshold",
    "holiday_mode_boolean_entity": "input_boolean.holiday_mode",
    "holiday_start_datetime_entity": "input_datetime.holiday_start",
    "holiday_end_datetime_entity": "input_datetime.holiday_end",
    "auto_tune_inertia_entity": "input_boolean.autotune_inertia",
    "hourly_forecast_temperatures_entity": "input_text.hourly_forecast_temperatures",
}


class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for pumpsteer."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the config flow."""
        errors = {}

        if user_input is not None:
            # Add hardcoded entities to user_input
            combined_data = {**user_input, **HARDCODED_ENTITIES}

            # Validate that all entities exist
            errors = await self._validate_entities(combined_data)

            if not errors:
                return self.async_create_entry(title="PumpSteer", data=combined_data)

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
        """Validate that all required entities exist and are available."""
        errors = {}

        # Only the entities that the user actually selects
        user_selected_entities = [
            "indoor_temp_entity",
            "real_outdoor_entity",
            "electricity_price_entity",
        ]

        # Hardcoded entities that should always exist
        hardcoded_entities = {
            "hourly_forecast_temperatures_entity": "Temperature forecast input_text",
            "target_temp_entity": "Target temperature input_number",
            "summer_threshold_entity": "Summer threshold input_number",
            "holiday_mode_boolean_entity": "Holiday mode boolean",
            "holiday_start_datetime_entity": "Holiday start datetime",
            "holiday_end_datetime_entity": "Holiday end datetime",
            "auto_tune_inertia_entity": "Autotune inertia boolean",
        }

        # Check user-selected entities (block if missing)
        for field in user_selected_entities:
            entity_id = user_input.get(field)
            if not entity_id:
                errors[field] = f"Required: {field}"
                continue

            if not await self._entity_exists(entity_id):
                errors[field] = "required"
            elif not await self._entity_available(entity_id):
                errors[field] = "entity_unavailable"

        # Check hardcoded entities (warn only, do not block)
        for field, description in hardcoded_entities.items():
            entity_id = user_input.get(field)
            if entity_id:
                if not await self._entity_exists(entity_id):
                    _LOGGER.warning(
                        "Hardcoded entity not found: %s (%s) - This should be created by the package",
                        entity_id,
                        description,
                    )
                elif not await self._entity_available(entity_id):
                    _LOGGER.warning(
                        "Hardcoded entity unavailable: %s (%s) - Check package configuration",
                        entity_id,
                        description,
                    )

        return errors

    async def _entity_exists(self, entity_id: str) -> bool:
        """Check if entity exists in Home Assistant."""
        return self.hass.states.get(entity_id) is not None

    async def _entity_available(self, entity_id: str) -> bool:
        """Check if entity is available (not unavailable or unknown)."""
        entity = self.hass.states.get(entity_id)
        if not entity:
            return False
        return entity.state not in [
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            "unavailable",
            "unknown",
        ]

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return PumpSteerOptionsFlowHandler()
