import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import selector
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"

HARDCODED_ENTITIES = {
    "target_temp_entity": "input_number.indoor_target_temperature",
    "summer_threshold_entity": "input_number.pumpsteer_summer_threshold",
    "holiday_mode_boolean_entity": "input_boolean.holiday_mode",
    "holiday_start_datetime_entity": "input_datetime.holiday_start",
    "holiday_end_datetime_entity": "input_datetime.holiday_end",
    "auto_tune_inertia_entity": "input_boolean.autotune_inertia",
    "hourly_forecast_temperatures_entity": "input_text.hourly_forecast_temperatures",
}


class PumpSteerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for pumpsteer"""

    async def async_step_init(self, user_input=None):
        """Manage the options flow"""
        errors = {}

        entry = self.config_entry

        if user_input is not None:
            combined_data = {**user_input, **HARDCODED_ENTITIES}
            errors = await self._validate_entities(combined_data)

            if not errors:
                updated_data = entry.data.copy()
                updated_data.update(combined_data)

                self.hass.config_entries.async_update_entry(entry, data=updated_data)

                return self.async_create_entry(title="", data={})

        current_data = entry.data

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
                        default=current_data.get("electricity_price_entity"),
                    ): selector({"entity": {"domain": "sensor"}}),
                }
            ),
            errors=errors,
        )

    async def _validate_entities(self, user_input):
        """Validate that entities exist and are available"""
        errors = {}

        user_configurable_entities = {
            "indoor_temp_entity": "Indoor temperature sensor",
            "real_outdoor_entity": "Outdoor temperature sensor",
            "electricity_price_entity": "Electricity price sensor",
        }

        hardcoded_entities = {
            "hourly_forecast_temperatures_entity": "Temperature forecast input_text",
            "target_temp_entity": "Target temperature input_number",
            "summer_threshold_entity": "Summer threshold input_number",
            "holiday_mode_boolean_entity": "Holiday mode boolean",
            "holiday_start_datetime_entity": "Holiday start datetime",
            "holiday_end_datetime_entity": "Holiday end datetime",
            "auto_tune_inertia_entity": "Autotune inertia boolean",
        }

        for field, description in user_configurable_entities.items():
            entity_id = user_input.get(field)
            if not entity_id:
                errors[field] = f"Required: {description}"
                continue

            if not await self._entity_exists(entity_id):
                errors[field] = f"Entity not found: {entity_id}"
            elif not await self._entity_available(entity_id):
                errors[field] = f"Entity unavailable: {entity_id}"

        for field, description in hardcoded_entities.items():
            entity_id = user_input.get(field)
            if entity_id:
                if not await self._entity_exists(entity_id):
                    _LOGGER.warning(
                        "Hardcoded entity not found: %s (%s) - Check package configuration",
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
        """Check if entity exists"""
        return self.hass.states.get(entity_id) is not None

    async def _entity_available(self, entity_id: str) -> bool:
        """Check if entity is available"""
        entity = self.hass.states.get(entity_id)
        if not entity:
            return False
        return entity.state not in [
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            "unavailable",
            "unknown",
        ]
