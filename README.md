# PumpSteer

PumpSteer is a custom Home Assistant integration that dynamically adjusts your heat pump by manipulating the outdoor temperature sensor input. It leverages electricity price forecasts, indoor temperature, and weather data to optimize energy use.

---

## ✨ Features

* ✅ AI-based virtual outdoor temperature
* ✅ Adjusts based on indoor temperature, target, price and forecast
* ✅ Pre-boost mode for building heat buffer before price peaks
* ✅ Braking mode for saving energy during peak hours
* ✅ Comfort profiles supported (heating, neutral, braking, summer, preboost)
* ✅ Fully local, no cloud dependencies
* ✅ Configurable aggressiveness and house inertia
* ✅ ApexCharts template ready

---

## ⚙ Setup Instructions

### Required Entities:

| Entity Type               | Description                                                         |
| ------------------------- | ------------------------------------------------------------------- |
| `sensor`                  | Indoor temperature sensor                                           |
| `sensor`                  | Real outdoor temperature sensor                                     |
| `sensor`                  | Electricity price entity (e.g. Nordpool)                            |
| `input_text`              | Hourly forecast temperatures in CSV format (e.g. `"-4.5,-5.0,..."`) |
| `input_number`            | Target indoor temperature                                           |
| `input_number`            | Summer threshold (above this value disables heating)                |
| `input_number` (optional) | Aggressiveness level (0.0–3.0)                                      |
| `input_number` (optional) | House inertia (updated automatically if not set)                    |

---

## ✏ input\_text Format

The `input_text` for forecast must contain **24 comma-separated hourly values** representing temperatures:

```text
-5.1,-5.3,-5.7,-5.6,-5.5,... (24 total)
```

If the string is missing or malformed, a warning will be logged, and PumpSteer will pause until valid input is provided.

---

## 🔢 Sensor Values and Attributes

### `sensor.pumpsteer`:

**State**: A fake outdoor temperature (`float`) to feed your heat pump.

**Attributes:**

| Attribute                  | Description                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------- |
| `status`                   | "OK", or message about missing data                                                |
| `mode`                     | One of: `heating`, `neutral`, `braking`, `summer_mode`, `preboost`, `braking_mode` |
| `real_outdoor_temperature` | Current outdoor temp                                                               |
| `target_temperature`       | User-defined desired indoor temperature                                            |
| `indoor_temperature`       | Current measured indoor temperature                                                |
| `inertia`                  | Calculated or user-defined house inertia                                           |
| `aggressiveness`           | Strategy strength (0 = passive, 3 = aggressive)                                    |
| `summer_threshold`         | Threshold for disabling heating                                                    |
| `price_forecast`           | List of hourly electricity prices (from sensor attribute)                          |
| `preboost_active`          | `true` if pre-boost or braking is active                                           |

---

## 🌍 ApexCharts Example

```yaml
- type: custom:apexcharts-card
  graph_span: 24h
  span: 1h
  header:
    title: PumpSteer Mode & Virtual Temp
  series:
    - entity: sensor.pumpsteer
      name: Fake Outdoor Temp
      type: line
    - entity: sensor.outdoor_temperature
      name: Real Outdoor Temp
      type: line
    - entity: sensor.indoor_temperature
      name: Indoor Temp
      type: line
  yaxis:
    - id: temp
      min: -20
      max: 30
```

---

## 🚫 CSV Validation (Robustness)

In `sensor.py`, the hourly forecast is expected as a valid CSV string. If it's missing, invalid, or fewer than `lookahead_hours` values, a warning is logged and the sensor sets its state to `unavailable`.

Suggested future improvement: add explicit format validation and friendly log message if format is not parseable.

---

## ⚛ Developer: Improving Testability

To allow easier testing and mocking:

* Move complex blocks like fake temperature calculation to helper functions:

```python
# Instead of inline logic
fake_temp = real_outdoor_temp + (diff * scaling_factor)

# Use a helper
fake_temp = calculate_virtual_temp(real_outdoor_temp, indoor_temp, target_temp, aggressiveness)
```

* Split preboost logic out for testing scenarios
* Add `sensor_mode` decision as a pure function to allow for simulation testing

---

## 📄 License

MIT

---

## 👀 Links

* [GitHub Repository](https://github.com/JohanAlvedal/pumpsteer)
* [Issue Tracker](https://github.com/JohanAlvedal/pumpsteer/issues)
