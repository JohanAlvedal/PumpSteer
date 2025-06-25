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

## Requirements

Before installing this integration, ensure you have:

* **HACS (Home Assistant Community Store):** This is the recommended way to install and manage custom integrations. If you prefer manual installation, you will need to copy the `pumpsteer` folder into your Home Assistant's `custom_components` directory.
* **Existing Home Assistant sensor entities for:**
    * Your **current indoor temperature**.
    * Your **current real outdoor temperature**.
    * **Electricity price forecasts**: A sensor that provides the electricity price for the current time and the next hours as a list in an attribute (typically named `today`, for example from [Nordpool](https://github.com/custom-components/nordpool) or [Tibber](https://www.home-assistant.io/integrations/tibber/) integrations).

### Helper Entities Required (from `pumpsteer.yaml`)

These helper entities **must be set up in your Home Assistant configuration before installing the PumpSteer integration.** They are included in the provided `pumpsteer.yaml` file, which you should add to your Home Assistant `packages` or `configuration.yaml`.

| Entity Name                         | Description                                                                                                        |
| :---------------------------------- | :----------------------------------------------------------------------------------------------------------------- |
| `input_number.indoor_target_temperature` | Your desired indoor target temperature.                                                                            |
| `input_number.pumpsteer_summer_threshold` | The outdoor temperature above which summer mode is active (heating suppressed).                                    |
| `input_number.pumpsteer_aggressiveness` | (Optional) Controls how responsive the system is to changing conditions.                                           |
| `input_number.house_inertia`        | (Optional) Represents your home's thermal inertia (can be manually overridden or learned).                         |
| `input_text.hourly_forecast_temperatures` | This helper stores a comma-separated forecast of outdoor temperatures (e.g., `"2.5,3.1,4.0,..."`) for pre-boost. You will configure an automation to populate this. |

## Installation Guide

**It is crucial that all required helper entities (from `pumpsteer.yaml`) are configured and Home Assistant is restarted *before* you proceed with installing the PumpSteer integration.**

1.  **Add Helper Entities to your Configuration:**
    * Copy the contents of the `pumpsteer.yaml` file into your Home Assistant `configuration.yaml` (e.g., directly under `input_number:` and `input_text:`) or place the file in your `packages` directory and include it.
    * **Restart Home Assistant** after adding these helper entities. This ensures they are created and available for selection.

2.  **Install PumpSteer Integration:**
    * **Via HACS (Recommended):**
        * Open HACS in your Home Assistant.
        * Go to "Integrations".
        * Click the three dots in the top right corner and select "Custom repositories".
        * Add `https://github.com/JohanAlvedal/PumpSteer` as the URL, select "Integration" as the category, and click "Add".
        * Search for "PumpSteer" in HACS and click "Download".
    * **Manually:**
        * Download or clone this repository.
        * Copy the entire `pumpsteer` folder into your Home Assistant `custom_components` directory: `<config>/custom_components/pumpsteer/`

3.  **Restart Home Assistant Again:** After installing the integration (whether via HACS or manually), you must perform another full restart of Home Assistant.

4.  **Configure PumpSteer in the Home Assistant UI:**
    * Go to Home Assistant's UI -> Settings -> Devices & Services -> Integrations.
    * Click "Add Integration" (bottom right `+` button) and search for "PumpSteer".
    * Follow the setup wizard, selecting the sensor entities and helper entities you created in Step 1. Ensure you select the correct `input_text.hourly_forecast_temperatures` for the hourly temperature forecast entity.

5.  **Set up Pre-boost Automation (Optional):**
    * If you plan to use the pre-boost feature, you need to create an automation that regularly populates the `input_text.hourly_forecast_temperatures` entity with a comma-separated list of future hourly temperatures.
    * An example automation is provided below. Adapt it to your specific weather integration (e.g., `weather.smhi`, `weather.openweathermap`, etc.).

#### Example Automation to Populate Hourly Forecast (for pre-boost)

```yaml
alias: Update hourly forecast for PumpSteer
description: "Pulls hourly temperature forecasts from a weather entity and stores them in input_text.hourly_forecast_temperatures for PumpSteer's pre-boost feature."
mode: single
trigger:
  - platform: time_pattern
    minutes: "5" # Adjust update frequency as needed
  - platform: homeassistant # Trigger on Home Assistant start
    event: start
  - platform: event # Trigger on template reload (for development/testing)
    event_type: event_template_reloaded
action:
  - service: weather.get_forecasts # Use the official weather service
    target:
      entity_id: weather.smhi # CHANGE THIS to your actual weather entity (e.g., weather.openweathermap)
    data:
      type: hourly # Request hourly forecast data
    response_variable: forecast_result # Store the result in a variable
  - variables:
      # Extract temperatures for the next 6 hours (adjust [:6] if needed)
      hourly_forecast_data: >
        {% set forecast = forecast_result.get('weather.smhi', {}).get('forecast') %} {# CHANGE 'weather.smhi' to your entity_id #}
        {% if forecast is none or forecast == [] %}
          {{ [] }}
        {% else %}
          {{ forecast[:6] | map(attribute='temperature') | list }}
        {% endif %}
  - service: input_text.set_value
    target:
      entity_id: input_text.hourly_forecast_temperatures
    data:
      value: "{{ hourly_forecast_data | join(',') }}"
