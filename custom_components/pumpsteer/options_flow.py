import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.selector import selector

_LOGGER = logging.getLogger(__name__)

DOMAIN = "pumpsteer"


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
                errors = {**entity_errors}

                if not errors:
                    return self.async_create_entry(title="", data={**user_input})

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
                    vol.Optional(
                        "weather_entity",
                        default=current_data.get("weather_entity"),
                    ): selector({"entity": {"domain": "weather"}}),
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
                        "notify_service",
                        default=current_data.get("notify_service", ""),
                    ): selector({"text": {}}),
                    vol.Optional(
                        "preheat_boost_enabled",
                        default=current_data.get("preheat_boost_enabled", True),
                    ): selector({"boolean": {}}),
                }
            ),
            errors=errors,
        )

    def _validate_entities(self, user_input):
        """Validate that entities exist and are available."""
        errors = {}

        required_entities = {
            "indoor_temp_entity": "Indoor temperature sensor",
            "real_outdoor_entity": "Outdoor temperature sensor",
            "electricity_price_entity": "Electricity price sensor",
            "price_tomorrow_entity": "Tomorrow electricity price sensor",
        }

        for field, description in required_entities.items():
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

        # weather_entity är valfri — validera bara om den är ifylld
        weather = user_input.get("weather_entity")
        if weather and not self._entity_exists(weather):
            errors["weather_entity"] = "entity_not_found"

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
