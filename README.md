# 🌡️ PumpSteer Home Assistant Integration

## ![PumpSteer Logo](https://github.com/JohanAlvedal/PumpSteer/blob/main/icons/icon.png) ## Overview

`PumpSteer` is a custom Home Assistant integration that creates a dynamic, virtual outdoor temperature sensor. This sensor is designed to provide more intelligent control of your heat pump or boiler by adjusting the reported outdoor temperature based on several key factors: your indoor temperature, real-time and future electricity prices, optional weather forecasts, and your home's thermal inertia.

The primary goal is to optimize your home's heating for both comfort and cost-efficiency. For instance, it can "pre-boost" your heating during periods of cheap electricity or reduce heating when it's not needed, even if the actual outdoor temperature might suggest otherwise.

## Features

* **Adaptive Temperature Control:** Adjusts the virtual outdoor temperature dynamically based on the difference between your current indoor temperature and your desired target temperature.
* **Optional Pre-boost Functionality:** Proactively heats your home by setting a very low virtual outdoor temperature when cold conditions are expected *and* electricity prices are high. This feature helps to "store" heat in your home during favorable price periods.
* **Summer Mode Override:** Automatically sets a high virtual outdoor temperature to effectively turn off heating when the actual outdoor temperature exceeds a user-defined threshold, preventing unnecessary cooling or heating.
* **Aggressiveness Control:** Allows you to fine-tune how quickly and strongly the system reacts to temperature deviations and price signals.
* **Home Thermal Inertia Learning:** The integration includes logic to calculate your home's thermal inertia (how well it retains heat) for more precise and efficient adjustments. This calculated value can also be manually overridden by the user.
* **Local Operation:** All calculations and logic run entirely within your Home Assistant instance, without relying on external cloud services.

## Prerequisites

To use the `PumpSteer` integration, you need:

* Home Assistant version 2023.12 or newer.
* Access to the Home Assistant file system (e.g., via Samba Share or File Editor add-on) for manual installation.
* Existing Home Assistant sensor entities for:
    * Your **current indoor temperature**.
    * Your **current real outdoor temperature**.
    * **Electricity price forecasts** (a sensor that exposes future hourly prices as a list in an attribute, typically named `today`, for example from [Nordpool](https://github.com/custom-components/nordpool) or [Tibber](https://www.home-assistant.io/integrations/tibber/) integrations).

* You will also need the following [Home Assistant Helper entities](#helper-entities-recommended-packages-file), which are configured in your `configuration.yaml` or via the Home Assistant UI:
    * `input_number.indoor_target_temperature`: Your desired indoor temperature setting.
    * `input_number.pumpsteer_summer_threshold`: The outdoor temperature at which heating should be suppressed (summer mode).
    * `input_number.pumpsteer_aggressiveness` (Optional, Recommended): Controls the overall responsiveness of the system.
    * `input_number.house_inertia` (Optional): Allows manual adjustment or override of the calculated house inertia.

### For Pre-boost Feature (Optional)

To enable the intelligent pre-boost functionality, you must additionally provide:

* **`input_text.hourly_forecast_temperatures`**: This `input_text` entity must be *regularly updated* by a Home Assistant automation you create. It should contain a comma-separated string of future hourly temperature forecasts (e.g., `"2.5,3.1,4.0,..."`).

    Here's an **example automation** to populate `input_text.hourly_forecast_temperatures`. **You will need to adjust `weather.smhi` to match your specific weather integration's entity ID and ensure it provides a `forecast` attribute with hourly temperature data.**

    ```yaml
    # Example automation to update input_text.hourly_forecast_temperatures
    alias: Update Weather Forecast for PumpSteer Pre-boost
    description: Fills the input_text helper with comma-separated temperature forecasts for PumpSteer.
    trigger:
      - platform: time_pattern
        minutes: "5" # Runs every hour at xx:05
    condition: []
    action:
      - service: input_text.set_value
        target:
          entity_id: input_text.hourly_forecast_temperatures # This is the input_text you select in the PumpSteer configuration
        data_template:
          value: >
            {% set forecast = state_attr('weather.smhi', 'forecast') %} {# !!! IMPORTANT: Adjust 'weather.smhi' to your actual weather entity !!! #}
            {% set temps = [] %}
            {# Extract temperatures for the next 6 hours. Adjust 'loop.index <= 6' if your pre_boost.py `lookahead_hours` is different. #}
            {% for item in forecast | list | selectattr('temperature', 'is_number') | list %}
              {% if loop.index <= 6 %}
                {% set temps = temps + [item.temperature] %}
              {% endif %}
            {% endfor %}
            {{ temps | join(',') }}
    mode: single
    ```

## Installation

### Manual Installation (Recommended for Development and Advanced Users)

1.  **Create Custom Component Folder:** In your Home Assistant configuration directory (`config/`), create a new folder named `custom_components`.
2.  **Download Integration Files:** Inside `custom_components/`, create another folder named `PumpSteer`.
3.  **Copy Files:** Copy all files from this repository (specifically `__init__.py`, `config_flow.py`, `const.py`, `manifest.json`, `options_flow.py`, `pre_boost.py`, `sensor.py`, and `info.md`) into the `config/custom_components/pumpsteer/` folder.
    Your folder structure should look like this:

    ```
    <config_dir>/
    └── custom_components/
        └── pumpsteer/
            ├── __init__.py
            ├── config_flow.py
            ├── const.py
            ├── manifest.json
            ├── options_flow.py
            ├── pre_boost.py
            ├── sensor.py
            └── info.md
    ```
4.  **Restart Home Assistant:** Go to **Settings** -> **System** -> **Restart** to ensure Home Assistant discovers the new integration.

## Configuration

The `PumpSteer` integration is configured via the Home Assistant User Interface (UI Config Flow).

1.  **Add Integration:** After restarting Home Assistant, navigate to **Settings** -> **Devices & Services** -> **Integrations** tab.
2.  Click the **"Add Integration"** button (blue circle with a plus sign in the bottom right).
3.  Search for "PumpSteer" and select it from the list.
4.  **Follow the On-Screen Prompts:** The configuration flow will guide you to select the necessary sensor and `input_number`/`input_text` entities. Ensure you select the helper entities you have defined (see [Helper Entities](#helper-entities-recommended-packages-file) below), for example:
    * **Indoor Temperature Sensor:** Select your sensor reporting current indoor temperature.
    * **Real Outdoor Temperature Sensor:** Select your sensor reporting current real outdoor temperature.
    * **Electricity Price Forecast Sensor:** Select your electricity price sensor (e.g., `sensor.nordpool_spot_prices`).
    * **Weather Forecast Entity (Optional):** Select `input_text.hourly_forecast_temperatures`. Leave this field blank if you do not wish to use the pre-boost feature based on weather forecasts.
    * **Target Temperature Entity:** Select `input_number.indoor_target_temperature`.
    * **Summer Threshold Entity:** Select `input_number.pumpsteer_summer_threshold`.

After successful configuration, a new sensor entity named `sensor.virtual_outdoor_temp` will be created in your Home Assistant instance.

## Usage

The `sensor.virtual_outdoor_temp` entity reports the calculated virtual outdoor temperature in degrees Celsius (`°C`). This sensor's state is designed to be used as an input signal to your heat pump's or boiler's control system, particularly those that adjust heating based on an outdoor temperature input (e.g., by overriding a built-in outdoor sensor).

The sensor also exposes several useful attributes providing insight into its current state and calculations:

* `Innetemp`: Current indoor temperature (`sensor.your_indoor_temp`).
* `Måltemp`: The set target indoor temperature (`input_number.indoor_target_temperature`).
* `Elpris`: The current electricity price from your selected sensor.
* `Ute (verklig)`: The current real outdoor temperature (`sensor.your_real_outdoor_temp`).
* `Sommartröskel`: The configured summer mode activation threshold (`input_number.pumpsteer_summer_threshold`).
* `Tröghet`: The calculated or manually set thermal inertia of your home.
* `Delta till mål`: The temperature difference between `Innetemp` and `Måltemp`.
* `Aggressivitet`: The current aggressiveness setting (`input_number.pumpsteer_aggressiveness`).
* `scaling_factor`: An internal calculated factor used in the virtual temperature determination.
* `Läge`: The current operating mode of the virtual sensor (e.g., `heating`, `braking/neutral`, `pre_boost`, `summer_mode`, `unavailable`).
* `Virtuell UteTemp`: A duplicate of the sensor's main state, included as an attribute for convenience.

To implement effective heating control, you will typically integrate `sensor.virtual_outdoor_temp` with your heat pump's control system or via Home Assistant automations that interact with your heating equipment. Consult your heat pump's manual or smart home integration documentation for details on how to utilize an external temperature signal.

## Helper Entities (Recommended `packages` file)

It is highly recommended to define the required `input_number` and `input_text` helper entities using Home Assistant's [Packages feature](https://www.home-assistant.io/docs/configuration/packages/). This method helps keep your Home Assistant configuration organized, modular, and easier to manage.

You can create a file (e.g., `virtual_outdoor_temp_helpers.yaml`) inside a `packages/` directory in your Home Assistant configuration folder and include it in your `configuration.yaml`.

First, ensure `packages` are included in your `configuration.yaml`:

```yaml
# configuration.yaml
homeassistant:
  packages: !include_dir_named packages/
