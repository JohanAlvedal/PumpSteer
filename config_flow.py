import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import selector

DOMAIN = "pumpsteer"

class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for pumpsteer."""

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="PumpSteer", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("indoor_temp_entity"): selector({"entity": {"domain": "sensor"}}),
                vol.Required("real_outdoor_entity"): selector({"entity": {"domain": "sensor"}}),
                vol.Required("electricity_price_entity"): selector({"entity": {"domain": "sensor"}}),
                vol.Required("hourly_forecast_temperatures_entity"): selector({"entity": {"domain": "input_text"}}), # ÄNDRAD RAD
                vol.Required("target_temp_entity"): selector({"entity": {"domain": "input_number"}}),
                vol.Required("summer_threshold_entity"): selector({"entity": {"domain": "input_number"}}),
            })
        )
