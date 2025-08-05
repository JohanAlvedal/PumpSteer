import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.selector import selector
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

# Import your OptionsFlowHandler here
from .options_flow import PumpSteerOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

# Hårdkodade entiteter som alltid finns i paketfilen
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
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Lägg till hårdkodade entiteter till user_input
            combined_data = {**user_input, **HARDCODED_ENTITIES}

            # Validera att entities existerar
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

        # Endast de entiteter som användaren faktiskt väljer
        user_selected_entities = {
            "indoor_temp_entity": "Indoor temperature sensor",
            "real_outdoor_entity": "Outdoor temperature sensor",
            "electricity_price_entity": "Electricity price sensor",
        }

        # Hårdkodade entiteter som alltid ska finnas
        hardcoded_entities = {
            "hourly_forecast_temperatures_entity": "Temperature forecast input_text",
            "target_temp_entity": "Target temperature input_number",
            "summer_threshold_entity": "Summer threshold input_number",
            "holiday_mode_boolean_entity": "Holiday mode boolean",
            "holiday_start_datetime_entity": "Holiday start datetime",
            "holiday_end_datetime_entity": "Holiday end datetime",
        }

        # Kontrollera användarvalda entiteter (blockerar om de saknas)
        for field, description in user_selected_entities.items():
            entity_id = user_input.get(field)
            if not entity_id:
                errors[field] = f"Required: {description}"
                continue

            if not await self._entity_exists(entity_id):
                errors[field] = f"Entity not found: {entity_id}"
            elif not await self._entity_available(entity_id):
                errors[field] = f"Entity unavailable: {entity_id}"

        # Kontrollera hårdkodade entiteter (bara varna, inte blockera)
        for field, description in hardcoded_entities.items():
            entity_id = user_input.get(field)
            if entity_id:
                if not await self._entity_exists(entity_id):
                    _LOGGER.warning(
                        f"Hardcoded entity not found: {entity_id} ({description}) - This should be created by the package"
                    )
                elif not await self._entity_available(entity_id):
                    _LOGGER.warning(
                        f"Hardcoded entity unavailable: {entity_id} ({description}) - Check package configuration"
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
        return PumpSteerOptionsFlowHandler(config_entry)
