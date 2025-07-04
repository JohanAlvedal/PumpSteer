
# PumpSteer

PumpSteer is a custom Home Assistant integration for dynamically optimizing your heat pump by manipulating the outdoor temperature sensor input. It allows you to save energy and money by adapting your heating strategy based on electricity prices, indoor temperature, and weather forecasts.

-----

## ✅ Features

  - 🔧 **Smart virtual outdoor temperature control**
  - ⚡ Adjusts heating strategy based on:
      - Indoor temperature
      - Target temperature
      - Electricity price forecast
      - Temperature forecast
  - 🌡️ Fake outdoor temperature is calculated to trick the heat pump into saving or buffering energy
  - 🚀 **Pre-boost mode:** build up a heat buffer before cold and expensive price peaks
  - 🧊 **Braking mode:** avoid heating during the most expensive hours
  - 🏖️ **Summer mode:** disables fake temperature when the outdoor temp is above the threshold
  - 🏝️ **Holiday Mode:** When Holiday Mode is on and the current time is within the selected dates, it will lower indoor temp to 16 degrees until you’re back.
  - 📦 **Easy setup** with a provided `packages` file for helper entities
  - 📊 Fully local (no cloud dependencies)
  - 🧠 Self-adjusting house inertia calculation
  - 🔄 Supports comfort profiles via an aggressiveness setting
  - 📈 ApexCharts examples included for visualization

-----

## Add PumpSteer to HACS as a Custom Repository

If PumpSteer is not yet available in the default HACS store, you can add it manually as a custom repository:

In Home Assistant, go to HACS in the sidebar.
Click the three dots menu (⋮) in the top right corner, and select Custom repositories.
In the "Repository" field, enter:
Code
https://github.com/JohanAlvedal/PumpSteer
Set the category to Integration.
Click Add.
PumpSteer will now appear under HACS > Integrations. Click Install to add it.
Restart Home Assistant after installation.
Continue with the configuration steps as described above.
Note:
As long as PumpSteer is not in the official HACS store, you need to repeat these steps if you reinstall HACS or clear its configuration.

-----

## 🔧 Installation & Configuration

Follow these three steps to get PumpSteer up and running.

### Step 1: Create Helper Entities (via Packages)

To make setup as easy as possible, this project includes a package file that creates all the necessary `input_number` and `input_text` helpers for you.

1.  **Download the `pumpsteer_package.yaml` file** from the repository.

2.  Place this file in your `/config/packages/` directory. If the `packages` directory does not exist at the root of your `/config` folder, you will need to create it.

3.  **Enable packages** in your main `configuration.yaml` file. If you haven't already, add the following lines. If you already have a `homeassistant:` section, just add the `packages:` line to it.

    ```yaml
    homeassistant:
      packages: !include_dir_named packages
    ```

4.  **Restart Home Assistant.** After restarting, all the required helpers (listed in the "Helper Entities Reference" section below) will be available.

### Step 2: Install the Custom Component

This is the standard procedure for installing a custom component.

1.  Place the `pumpsteer` directory (which contains `sensor.py`, `pre_boost.py`, etc.) in your Home Assistant `custom_components` folder.
2.  Restart Home Assistant again.

### Step 3: Add the Integration

1.  Navigate to **Settings \> Devices & Services \> Add Integration**.
2.  Search for and select **PumpSteer**.
3.  In the configuration dialog, select the helper entities that were created by the package file.

-----

## 📄 Helper Entities Reference

Using the provided `pumpsteer_package.yaml` file will create the following entities. You can adjust their values from the Home Assistant UI in **Settings \> Devices & Services \> Helpers**.

| Type | Description |
| :--- | :--- |
| `sensor` | Indoor temperature sensor (you must provide this) |
| `sensor` | Real outdoor temperature sensor (you must provide this) |
| `sensor` | Electricity price sensor (you must provide this, e.g., Nordpool or Tibber) |
| `input_text` | Stores the hourly forecast temperatures (CSV string, 24 values) |
| `input_number`| Your desired target indoor temperature |
| `input_number`| The outdoor temperature threshold for activating Summer Mode |
| `input_number` | The aggressiveness level for savings vs. comfort (0.0 to 5.0) |
| `input_number` | The calculated house inertia (you can let PumpSteer manage this or override it) |

-----

## 🧪 Forecast Format

The `input_text` entity for the temperature forecast must contain **of max 24 comma-separated values** representing the hourly forecasted outdoor temperatures for the next 24 hours:

```text
-3.5,-4.2,-5.0,-4.8,... (24 values total)
```

If the string is invalid or incomplete, the sensor will log a warning and temporarily suspend calculations until valid data is available.

-----

## 📊 Sensor Outputs

PumpSteer creates two sensors.

### 1\. `sensor.pumpsteer` (Control Sensor)

This sensor provides the calculated virtual temperature.

**State:** The fake outdoor temperature (`°C`) that should be sent to your heat pump.

**Attributes:**

| Attribute | Meaning |
| :--- | :--- |
| `Läge` | The current operating mode. Can be: `heating`, `neutral`, `braking_by_temp`, `summer_mode`, `preboost`, `braking_mode` |
| `Ute (verklig)` | The current temperature from the real outdoor sensor |
| `Inne (mål)` | Your desired indoor temperature |
| `Inne (verklig)` | The current indoor temperature |
| `Inertia` | How slowly the house reacts to outdoor temp changes (higher = better insulated) |
| `Aggressiveness` | From 0.0 (passive) to 5.0 (aggressive saving) |
| `Summer threshold` | The outdoor temp threshold to disable heat control |
| `Elpriser (prognos)` | Hourly electricity prices from your price sensor |
| `Pre-boost Aktiv` | True if pre-boost or braking is active (pauses inertia calculation) |

### 2\. `sensor.pumpsteer_future_strategy` (Diagnostic Sensor)

This sensor provides insights into *why* the system is making its decisions.

**State:**
The number of upcoming hours that are identified as both cold and expensive.

**Attributes:**

| Attribute | Meaning |
| :--- | :--- |
| `preboost_expected_in_hours` | How many hours in advance the system will start pre-boosting, based on house inertia. |
| `first_preboost_hour` | The clock time (e.g., "18:00") for the next expected pre-boost event. |
| `cold_and_expensive_hours_next_6h` | Total number of hours identified as "cold & expensive" in the next 6 hours. |
| `expensive_hours_next_6h` | Total number of hours considered "expensive" in the next 6 hours. |
| `braking_price_threshold_percent` | The current price threshold (as % of max price) for activating braking mode. |

-----

## Aggressiveness – What Does It Do?

Aggressiveness (0.0 to 5.0) controls the trade-off between energy savings and indoor comfort. It affects both when heating is reduced (braking) and when extra heating is added (pre-boost).

| Setting | Braking behavior | Pre-boost behavior |
| :--- | :--- | :--- |
| **Low** (e.g., 0-1) | Rarely brakes, only at the absolute highest prices. | Boosts more easily to prioritize comfort. |
| **High** (e.g., 4-5) | Brakes early and often, even for moderate price peaks. | Boosts only in the most necessary cases to save energy. |

**Higher aggressiveness saves more money, but may reduce indoor comfort.**

-----

## 📈 ApexCharts Examples

### Visualizing Temperatures

```yaml
type: custom:apexcharts-card
header:
  title: PumpSteer Temperature Control
graph_span: 24h
span:
  start: day
series:
  - entity: sensor.pumpsteer
    name: Fake Outdoor Temp
  - entity: sensor.ute_verklig_temp
    name: Real Outdoor Temp
  - entity: sensor.inne_verklig_temp
    name: Indoor Temp
  - entity: input_number.varmepump_target_temp
    name: Target Temp
    stroke_width: 2
    curve: stepline
```

### Visualizing Future Strategy

```yaml
type: custom:apexcharts-card
header:
  title: PumpSteer - Future Threats
chart_type: bar
graph_span: 24h
series:
  - entity: sensor.pumpsteer_future_strategy
    name: Cold & Expensive Hours
    attribute: cold_and_expensive_hours_next_6h
  - entity: sensor.pumpsteer_future_strategy
    name: Expensive Hours
    attribute: expensive_hours_next_6h
```

-----

## 🧠 How It Works

PumpSteer calculates a "fake" outdoor temperature to nudge your heat pump to either:

  - **Pre-boost:** Heat more when prices and temperatures are low, before an upcoming cold and expensive peak.
  - **Brake:** Avoid heating when prices are at their highest.
  - **Normal:** Gently adjust heating to maintain comfort with minimal cost.
  - **Summer Mode:** Stand down when it's warm outside.

-----

## 💬 Logging and Troubleshooting

  - Warnings and errors are logged to the standard Home Assistant log.
  - If required sensor data is unavailable, PumpSteer will show `unavailable` and retry automatically.
  - The house inertia value is calculated and updated automatically unless you provide a manual override via an `input_number`.

-----

## A Note From The Developer

This integration was built by an amateur developer with the powerful assistance of Google's Gemini. It is the result of a passion for smart homes, a lot of trial and error, and many, many Home Assistant restarts.

Please consider this a **beta product** in the truest sense.

If you are knowledgeable in this area, constructive feedback, suggestions, and contributions are warmly welcomed. Please be patient, as this is a learning project.

-----

## 🔗 Links

  - [Issue Tracker](https://github.com/JohanAlvedal/pumpsteer/issues)

-----

## 📄 License

MIT © Johan Älvedal
