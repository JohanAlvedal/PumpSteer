import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import selector

DOMAIN = "pumpsteer"

class PumpSteerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # Saving to data to ensure compatibility with how sensor.py reads config
            return self.async_create_entry(title="PumpSteer Options", data=user_input)

        # Fetch current values from config_entry.data for defaults in the form
        current_indoor_temp = self.config_entry.data.get("indoor_temp_entity")
        current_real_outdoor = self.config_entry.data.get("real_outdoor_entity")
        current_electricity_price = self.config_entry.data.get("electricity_price_entity")
        current_hourly_forecast = self.config_entry.data.get("hourly_forecast_temperatures_entity")
        current_target_temp = self.config_entry.data.get("target_temp_entity")
        current_summer_threshold = self.config_entry.data.get("summer_threshold_entity")

        # Get current Holiday Mode values (new fields)
        current_holiday_mode_boolean = self.config_entry.data.get("holiday_mode_boolean_entity")
        current_holiday_start_datetime = self.config_entry.data.get("holiday_start_datetime_entity")
        current_holiday_end_datetime = self.config_entry.data.get("holiday_end_datetime_entity")

        # This schema allows editing all fields, both required and optional.
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("indoor_temp_entity", default=current_indoor_temp): selector({"entity": {"domain": "sensor"}}),
                vol.Required("real_outdoor_entity", default=current_real_outdoor): selector({"entity": {"domain": "sensor"}}),
                vol.Required("electricity_price_entity", default=current_electricity_price): selector({"entity": {"domain": "sensor"}}),
                vol.Required("hourly_forecast_temperatures_entity", default=current_hourly_forecast): selector({"entity": {"domain": "input_text"}}),
                vol.Required("target_temp_entity", default=current_target_temp): selector({"entity": {"domain": "input_number"}}),
                vol.Required("summer_threshold_entity", default=current_summer_threshold): selector({"entity": {"domain": "input_number"}}),
                vol.Optional(
                    "holiday_mode_boolean_entity", 
                    default=current_holiday_mode_boolean
                ): selector({"entity": {"domain": "input_boolean"}}),
                vol.Optional(
                    "holiday_start_datetime_entity", 
                    default=current_holiday_start_datetime
                ): selector({"entity": {"domain": "input_datetime"}}),
                vol.Optional(
                    "holiday_end_datetime_entity", 
                    default=current_holiday_end_datetime
                ): selector({"entity": {"domain": "input_datetime"}}),
            })
        )
