import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import selector

DOMAIN = "pumpsteer"

class PumpSteerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        """Initialize PumpSteer options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # Update the existing config_entry.data with the user's changes.
            # This ensures that any fields not explicitly in user_input (e.g., if we had optional fields)
            # retain their previous values.
            updated_data = self.config_entry.data.copy()
            updated_data.update(user_input)
            return self.async_create_entry(title="PumpSteer Options", data=updated_data)

        # Fetch current values from config_entry.data for defaults in the form
        # Only fetch the entities that *are* configurable via this UI flow.
        current_indoor_temp = self.config_entry.data.get("indoor_temp_entity")
        current_real_outdoor = self.config_entry.data.get("real_outdoor_entity")
        current_electricity_price = self.config_entry.data.get("electricity_price_entity")
        current_hourly_forecast = self.config_entry.data.get("hourly_forecast_temperatures_entity")

        # The schema now only includes the sensor entities that the user needs to select.
        # Control parameters like target_temp, summer_threshold, aggressiveness, inertia,
        # and holiday mode entities are assumed to be fixed or managed by other HA helpers
        # (e.g., input_number, input_boolean, input_datetime) and are not part of this flow.
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("indoor_temp_entity", default=current_indoor_temp): selector({"entity": {"domain": "sensor"}}),
                vol.Required("real_outdoor_entity", default=current_real_outdoor): selector({"entity": {"domain": "sensor"}}),
                vol.Required("electricity_price_entity", default=current_electricity_price): selector({"entity": {"domain": "sensor"}}),
                vol.Required("hourly_forecast_temperatures_entity", default=current_hourly_forecast): selector({"entity": {"domain": "input_text"}}),
            })
        )
