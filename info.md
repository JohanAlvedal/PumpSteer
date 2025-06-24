# 🌡️ VirtualOutdoorTemp Home Assistant Integration

![VirtualOutdoorTemp Logo](https://raw.githubusercontent.com/JohanAlvedal/VirtuelOutdoorTemp/main/icons/icon.png) ## Overview

`VirtualOutdoorTemp` is a custom Home Assistant integration that creates a dynamic, virtual outdoor temperature sensor. This sensor is designed to provide more intelligent control of your heat pump or boiler by adjusting the reported outdoor temperature based on several key factors: your indoor temperature, real-time and future electricity prices, optional weather forecasts, and your home's thermal inertia.

The primary goal is to optimize your home's heating for both comfort and cost-efficiency. For instance, it can "pre-boost" your heating during periods of cheap electricity or reduce heating when it's not needed, even if the actual outdoor temperature might suggest otherwise.

## Features

* **Adaptive Temperature Control:** Adjusts the virtual outdoor temperature dynamically based on the difference between your current indoor temperature and your desired target temperature.
* **Optional Pre-boost Functionality:** Proactively heats your home by setting a very low virtual outdoor temperature when cold conditions are expected *and* electricity prices are high. This feature helps to "store" heat in your home during favorable price periods.
* **Summer Mode Override:** Automatically sets a high virtual outdoor temperature to effectively turn off heating when the actual outdoor temperature exceeds a user-defined threshold, preventing unnecessary cooling or heating.
* **Aggressiveness Control:** Allows you to fine-tune how quickly and strongly the system reacts to temperature deviations and price signals.
* **Home Thermal Inertia Learning:** The integration includes logic to calculate your home's thermal inertia (how well it retains heat) for more precise and efficient adjustments. This calculated value can also be manually overridden by the user.
* **Local Operation:** All calculations and logic run entirely within your Home Assistant instance, without relying on external cloud services.

## Prerequisites

To use the `VirtualOutdoorTemp` integration, you need:

* Home Assistant version 2023.12 or newer.
* Access to the Home Assistant file system (e.g., via Samba Share or File Editor add-on) for manual installation.
* Existing Home Assistant sensor entities for:
    * Your **current indoor temperature**.
    * Your **current real outdoor temperature**.
    * **Electricity price forecasts** (a sensor that exposes future hourly prices as a list in an attribute, typically named `today`, for example from [Nordpool](https://github.com/custom-components/nordpool) or [Tibber](https://www.home-assistant.io/integrations/tibber/) integrations).

* You will also need the following [Home Assistant Helper entities](#helper-entities-recommended-packages-file), which are configured in your `configuration.yaml` or via the Home Assistant UI:
    * `input_number.indoor_target_temperature`: Your desired indoor temperature setting.
    * `input_number.virtualoutdoortemp_summer_threshold`: The outdoor temperature at which heating should be suppressed (summer mode).
    * `input_number.virtualoutdoortemp_aggressiveness` (Optional, Recommended): Controls the overall responsiveness of the system.
    * `input_number.house_inertia` (Optional): Allows manual adjustment or override of the calculated house inertia.

### For Pre-boost Feature (Optional)

To enable the intelligent pre-boost functionality, you must additionally provide:

* **`input_text.hourly_forecast_temperatures`**: This `input_text` entity must be *regularly updated* by a Home Assistant automation you create. It should contain a comma-separated string of future hourly temperature forecasts (e.g., `"2.5,3.1,4.0,..."`).

