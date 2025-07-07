import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import selector

# Import your OptionsFlowHandler here
# Make sure your options_flow.py is in the same directory or correctly imported
from .options_flow import PumpSteerOptionsFlowHandler # This line is crucial!

DOMAIN = "pumpsteer"

class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for pumpsteer."""

    VERSION = 1  # Increment version if you make breaking changes to schema

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="PumpSteer", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("indoor_temp_entity"): selector({"entity": {"domain": "sensor"}}),
                vol.Required("real_outdoor_entity"): selector({"entity": {"domain": "sensor"}}),
                vol.Required("electricity_price_entity"): selector({"entity": {"domain": "sensor"}}),
                vol.Required("hourly_forecast_temperatures_entity"): selector({"entity": {"domain": "input_text"}}),
                vol.Required("target_temp_entity"): selector({"entity": {"domain": "input_number"}}),
                vol.Required("summer_threshold_entity"): selector({"entity": {"domain": "input_number"}}),
                # These are commented out here, which is fine if they are fixed input_number helpers
                # vol.Optional("aggressiveness_entity"): selector({"entity": {"domain": "input_number"}}),
                # vol.Optional("house_inertia_entity"): selector({"entity": {"domain": "input_number"}}),
            })
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        # This method tells Home Assistant to use PumpSteerOptionsFlowHandler
        # when the user clicks the "Configure" button for this integration.
        return PumpSteerOptionsFlowHandler(config_entry)
