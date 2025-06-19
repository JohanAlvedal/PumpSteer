from homeassistant import config_entries
import voluptuous as vol
from homeassistant.helpers.selector import selector

DOMAIN = "virtualoutdoortemp"

class VirtualOutdoorTempOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("indoor_temp_entity", default=self.config_entry.options.get("indoor_temp_entity")): selector({"entity": {"domain": "sensor"}}),
                vol.Required("real_outdoor_entity", default=self.config_entry.options.get("real_outdoor_entity")): selector({"entity": {"domain": "sensor"}}),
                vol.Required("electricity_price_entity", default=self.config_entry.options.get("electricity_price_entity")): selector({"entity": {"domain": "sensor"}}),
                vol.Required("weather_entity", default=self.config_entry.options.get("weather_entity")): selector({"entity": {"domain": "weather"}}),
                vol.Required("target_temp_entity", default=self.config_entry.options.get("target_temp_entity")): selector({"entity": {"domain": "input_number"}}),
            }),
        )
