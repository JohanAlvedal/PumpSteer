import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import selector

DOMAIN = "pumpsteer"

class PumpSteerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("indoor_temp_entity", default=self.config_entry.data.get("indoor_temp_entity")): selector({"entity": {"domain": "sensor"}}),
                vol.Required("real_outdoor_entity", default=self.config_entry.data.get("real_outdoor_entity")): selector({"entity": {"domain": "sensor"}}),
                vol.Required("electricity_price_entity", default=self.config_entry.data.get("electricity_price_entity")): selector({"entity": {"domain": "sensor"}}),
                vol.Required("hourly_forecast_temperatures_entity", default=self.config_entry.options.get("hourly_forecast_temperatures_entity")): selector({"entity": {"domain": "input_text"}}), # ÄNDRAD RAD
                vol.Required("target_temp_entity", default=self.config_entry.data.get("target_temp_entity")): selector({"entity": {"domain": "input_number"}}),
                vol.Required("summer_threshold_entity", default=self.config_entry.data.get("summer_threshold_entity")): selector({"entity": {"domain": "input_number"}}),
                vol.Optional("aggressiveness_entity", default=self.config_entry.options.get("aggressiveness_entity")): selector({"entity": {"domain": "input_number"}}),
                vol.Optional("house_inertia_entity", default=self.config_entry.options.get("house_inertia_entity")): selector({"entity": {"domain": "input_number"}}),
            })
        )
