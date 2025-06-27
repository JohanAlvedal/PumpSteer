# 🚀 PumpSteer – Smarter Heat Pump Control for Home Assistant

**PumpSteer** is a custom Home Assistant integration that dynamically optimizes your heat pump by manipulating the virtual outdoor temperature input. It helps you save energy and money by adjusting your heating strategy based on:

- Electricity price forecasts  
- Indoor and target temperatures  
- Hourly outdoor temperature forecasts

---

## ✅ Features

- 🔧 Smart virtual outdoor temperature control
- 🌡️ Calculates a "fake" outdoor temperature to trick your heat pump into saving or buffering energy
- 🚀 **Pre-boost mode** – pre-heat before expensive and cold periods
- 🧊 **Braking mode** – reduce heating during expensive hours
- 🏖️ **Summer mode** – disables control when outdoor temperature is high
- ⚙️ **Self-adjusting house inertia** (how slowly your home heats/cools)
- 🔄 Supports **comfort profiles** via an aggressiveness setting
- 📊 Includes **ApexCharts examples** for data visualization
- 📦 Easy setup with helper entities via YAML package
- 🔐 Fully local – no cloud dependencies

---

## 🔧 Installation & Configuration

### Step 1: Create Helper Entities (via Packages)

1. Download `pumpsteer_package.yaml` from the repository
2. Place it in `/config/packages/` (create the folder if it doesn’t exist)
3. Enable packages in your `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
````

4. Restart Home Assistant – all required helpers will now be created.

---

### Step 2: Install the Custom Component

1. Copy the `pumpsteer` directory (containing `sensor.py`, `pre_boost.py`, etc.) into `/config/custom_components/`
2. Restart Home Assistant again

---

### Step 3: Add the Integration via UI

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for and select **PumpSteer**
3. Choose the helper entities created by the package

---

## 📄 Helper Entities Reference

| Type           | Description                                                    |
| -------------- | -------------------------------------------------------------- |
| `sensor`       | Indoor temperature sensor *(you provide)*                      |
| `sensor`       | Real outdoor temperature sensor *(you provide)*                |
| `sensor`       | Electricity price sensor *(e.g., Nordpool or Tibber)*          |
| `input_text`   | 24-hour outdoor temperature forecast as comma-separated values |
| `input_number` | Desired indoor target temperature                              |
| `input_number` | Outdoor temp threshold for **Summer Mode**                     |
| `input_number` | Aggressiveness level (0.0 = comfort, 5.0 = maximum savings)    |
| `input_number` | House inertia (auto-calculated but can be overridden manually) |

---

## 🧪 Forecast Format

The `input_text` entity must contain 24 comma-separated outdoor temperatures:

```
-3.5,-4.2,-5.0,-4.8,... (total of 24 values)
```

If invalid or incomplete, PumpSteer will pause calculations until fixed.

---

## 📊 Sensor Outputs

### 1. `sensor.pumpsteer` – Control Sensor

**State**: The virtual outdoor temperature (°C) sent to your heat pump.

**Attributes:**

| Attribute            | Description                                                           |
| -------------------- | --------------------------------------------------------------------- |
| `Läge`               | Operating mode (e.g., `heating`, `braking_mode`, `summer_mode`, etc.) |
| `Ute (verklig)`      | Real outdoor temperature                                              |
| `Inne (mål)`         | Desired indoor temperature                                            |
| `Inne (verklig)`     | Current indoor temperature                                            |
| `Inertia`            | Calculated house thermal inertia                                      |
| `Aggressiveness`     | Comfort/savings trade-off (0.0–5.0)                                   |
| `Sommartröskel`      | Summer Mode threshold temperature                                     |
| `Elpriser (prognos)` | Hourly electricity prices                                             |
| `Pre-boost Aktiv`    | `true` if pre-boost or braking is active                              |

---

### 2. `sensor.pumpsteer_future_strategy` – Diagnostic Sensor

**State**: Number of upcoming hours identified as "cold & expensive".

**Attributes:**

| Attribute                          | Description                                          |
| ---------------------------------- | ---------------------------------------------------- |
| `preboost_expected_in_hours`       | Hours in advance for pre-boost, based on inertia     |
| `first_preboost_hour`              | Clock time for next expected pre-boost event         |
| `cold_and_expensive_hours_next_6h` | # of cold & expensive hours in next 6h               |
| `expensive_hours_next_6h`          | # of expensive hours in next 6h                      |
| `braking_price_threshold_percent`  | Threshold (as % of max price) for braking activation |
| `preboost_price_threshold_percent` | Price threshold (as % of max) used for pre-boost     |

---

## 🧠 How Aggressiveness Works

| Setting        | Braking Behavior                            | Pre-boost Behavior                  |
| -------------- | ------------------------------------------- | ----------------------------------- |
| **Low (0-1)**  | Rarely brakes (only on extreme price peaks) | Boosts easily for comfort           |
| **High (4-5)** | Brakes early/often                          | Boosts only if absolutely necessary |

**Higher values save more energy but may reduce comfort.**

---

## 📈 ApexCharts Examples

### Temperature Control Graph

```yaml
type: custom:apexcharts-card
header:
  title: PumpSteer Temperature Control
graph_span: 24h
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

---

### Future Threats Visualization

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

---

## 🔍 Logging & Troubleshooting

* Warnings and errors appear in Home Assistant's standard log
* If required data is missing, the sensor becomes `unavailable` and will retry
* Inertia is calculated automatically unless overridden

---

## 💬 A Note from the Developer

This integration was built by an amateur developer with the powerful assistance of Google's Gemini. It is the result of a passion for smart homes, a lot of trial and error, and many, many Home Assistant restarts.

Please consider this a beta product in the truest sense.

If you are knowledgeable in this area, constructive feedback, suggestions, and contributions are warmly welcomed. Please be patient, as this is a learning project.

---

## 🔗 Links

* [Issue Tracker](https://github.com/JohanAlvedal/pumpsteer/issues)
* [MIT License](LICENSE)

```

Vill du att jag även hjälper dig skapa en motsvarande `pumpsteer_package.yaml`-fil redo för uppladdning i repot?
```
