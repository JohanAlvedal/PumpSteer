# 🌡️ PumpSteer Home Assistant Integration

`PumpSteer` is a custom Home Assistant integration that creates a dynamic, virtual outdoor temperature sensor. This sensor is designed to provide more intelligent control of your heat pump or boiler by adjusting the reported outdoor temperature based on several key factors: your indoor temperature, real-time and future electricity prices, optional weather forecasts, and your home's thermal inertia.

The primary goal is to optimize your home's heating for both comfort and cost-efficiency. For instance, it can "pre-boost" your heating during periods of cheap electricity or reduce heating when it's not needed, even if the actual outdoor temperature might suggest otherwise.

## Features

* **Adaptive Temperature Control:** Adjusts the virtual outdoor temperature dynamically based on the difference between your current indoor temperature and your desired target temperature.
* **Optional Pre-boost Functionality:** Proactively heats your home by setting a very low virtual outdoor temperature when cold conditions are expected *and* electricity prices are high. This feature helps to "store" heat in your home during favorable price periods.
* **Summer Mode Override:** Automatically sets a high virtual outdoor temperature to effectively turn off heating when the actual outdoor temperature exceeds a user-defined threshold, preventing unnecessary cooling or heating.
* **Aggressiveness Control:** Allows you to fine-tune how quickly and strongly the system reacts to temperature differences and price fluctuations.
* **Thermal Inertia Adjustment:** Incorporates or allows manual override of your home's thermal inertia, influencing how the system reacts to changes over time.

## Requirements

Before installing this integration, ensure you have:

* **HACS (Home Assistant Community Store):** This is the recommended way to install and manage custom integrations. If you prefer manual installation, you will need to copy the `pumpsteer` folder into your Home Assistant's `custom_components` directory.
* **Existing Home Assistant sensor entities for:**
    * Your **current indoor temperature**.
    * Your **current real outdoor temperature**.
    * **Electricity price forecasts** (a sensor that exposes future hourly prices as a list in an attribute, typically named `today`, for example from [Nordpool](https://github.com/custom-components/nordpool) or [Tibber](https://www.home-assistant.io/integrations/tibber/) integrations).

## Installation Steps

Follow these steps carefully to install and set up PumpSteer:

1.  **Add Helper Entities:**
    * First, add the necessary Home Assistant Helper entities to your `configuration.yaml` file (or use a `packages` setup for better organization). You can find the required YAML configuration in the `pumpsteer.yaml` file provided with this integration.
    * **Crucially, restart Home Assistant after adding these helper entities.** This ensures they are created and available for selection in the next step.
    * The required helper entities are:
        * `input_number.indoor_target_temperature`: Your desired indoor temperature setting.
        * `input_number.pumpsteer_summer_threshold`: The outdoor temperature at which heating should be suppressed (summer mode).
        * `input_number.pumpsteer_aggressiveness` (Optional, Recommended): Controls the overall responsiveness of the system.
        * `input_number.house_inertia` (Optional): Allows manual adjustment or override of the calculated house inertia.
        * `input_text.hourly_forecast_temperatures`: This `input_text` entity will store your future hourly temperature forecasts.

2.  **Install PumpSteer Integration (via HACS or Manually):**
    * **HACS:** Add this repository (`https://github.com/JohanAlvedal/pumpsteer`) as a custom repository in HACS (Type: Integration). Then search for "PumpSteer" and install it.
    * **Manual:** Copy the entire `pumpsteer` folder (containing `__init__.py`, `config_flow.py`, etc.) into your Home Assistant's `custom_components` directory.

3.  **Restart Home Assistant Again:** After installing the integration (whether via HACS or manually), you must perform another full restart of Home Assistant.

4.  **Configure PumpSteer via Integrations:**
    * Go to Home Assistant's UI -> Settings -> Devices & Services -> Integrations.
    * Click "Add Integration" and search for "PumpSteer".
    * Follow the on-screen prompts to select the sensor entities and helper entities you created in Step 1. Ensure you select the correct `input_text` for hourly temperature forecasts.

### For Pre-boost Feature (Optional Automation)

To enable the intelligent pre-boost functionality, you must additionally set up an automation to populate the `input_text.hourly_forecast_temperatures` entity. An example automation (which you can adapt) is provided within the `pumpsteer.yaml` file. This `input_text` entity must be *regularly updated* by a Home Assistant automation you create, containing a comma-separated string of future hourly temperature forecasts (e.g., `"2.5,3.1,4.0,..."`).
