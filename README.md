# 🌡️ PumpSteer Home Assistant Integration

<img src="https://github.com/JohanAlvedal/PumpSteer/blob/main/icons/icon.png" alt="PumpSteer Logo" width="120" />

## English – Overview

PumpSteer is a custom Home Assistant integration that creates a dynamic, virtual outdoor temperature sensor. This sensor helps intelligently control your heat pump or boiler by adjusting the reported outdoor temperature based on indoor temperature, electricity price, weather forecast, and thermal inertia.

### Features

* Adaptive temperature control
* Optional pre-boost heating
* Summer mode override
* Aggressiveness control
* Learns your home's thermal inertia
* Fully local – no cloud dependency

### Required Entities

| Entity                                    | Description                                                                                                                                                       |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sensor.indoor_temperature`               | The sensor that reports the current indoor temperature.                                                                                                           |
| `sensor.real_outdoor_temperature`         | The sensor that reports the actual outdoor temperature.                                                                                                           |
| `sensor.electricity_price_forecast`       | A sensor that provides the electricity price for the current time and the next 6 hours.                                                                           |
| `input_text.hourly_forecast_temperatures` | A helper that stores a comma-separated forecast of outdoor temperatures for the next 6 hours. Populated via automation. Included in the provided `packages` file. |
| `input_number.indoor_target_temperature`  | A number helper representing your desired indoor target temperature. Included in the `packages` file.                                                             |
| `input_number.pumpsteer_summer_threshold` | A number helper representing the temperature threshold above which summer mode is active. Included in the `packages` file.                                        |

### Entities Included via the Packages File

These helpers and sensors are included automatically when using the provided `packages` file:

| Entity                                             | Description                                                   |
| -------------------------------------------------- | ------------------------------------------------------------- |
| `input_number.virtualoutdoortemp_aggressiveness`   | Controls how responsive the system is to changing conditions. |
| `input_number.virtualoutdoortemp_summer_threshold` | Sets the threshold above which summer mode is activated.      |
| `input_number.indoor_target_temperature`           | Defines your desired indoor temperature.                      |
| `input_number.house_inertia`                       | Represents your home's thermal inertia.                       |
| `input_text.hourly_forecast_temperatures`          | Stores 6-hour temperature forecast used for pre-boost.        |

### Installation Guide

**Note:** All required `input_number` and `input_text` helpers are already included in the default `packages` file provided with this integration. You only need to set up an automation to regularly populate `input_text.hourly_forecast_temperatures` if you plan to use the pre-boost feature.

#### Example automation to fill hourly forecast (if using pre-boost)

```yaml
alias: Update hourly forecast for PumpSteer
mode: single
trigger:
  - platform: time_pattern
    minutes: "5"
action:
  - service: input_text.set_value
    target:
      entity_id: input_text.hourly_forecast_temperatures
    data:
      value: >
        {% set forecast = state_attr('weather.smhi', 'forecast') %}
        {% if forecast is none %}unavailable{% else %}
        {% set temps = forecast[:6] | map(attribute='temperature') | list %}
        {{ temps | join(',') }}
        {% endif %}
```

1. **Download or clone this repository.**
2. Copy the folder `pumpsteer` into your Home Assistant custom components directory:

   ```
   <config>/custom_components/pumpsteer/
   ```
3. Make sure your `configuration.yaml` is properly set up for any needed `input_number`, `input_text`, and sensors.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Integrations**.
6. Click **"Add Integration"**, then search for **PumpSteer** and follow the setup wizard.
7. Done! You should now have a sensor called `sensor.virtual_outdoor_temp`.
   \| Description                                                  |
   \|-----------------------------------------------|--------------------------------------------------------------|
   \| `input_number.virtualoutdoortemp_aggressiveness` | Controls how responsive the system is to changing conditions. |
   \| `input_number.virtualoutdoortemp_summer_threshold` | Sets the threshold above which summer mode is activated.      |
   \| `input_number.indoor_target_temperature`       | Defines your desired indoor temperature.                     |
   \| `input_number.house_inertia`                  | Represents your home's thermal inertia.                      |
   \| `input_text.hourly_forecast_temperatures`     | Stores 6-hour temperature forecast used for pre-boost.       |
