
# PumpSteer

PumpSteer is a custom Home Assistant integration for dynamically optimizing your heat pump by manipulating the outdoor temperature sensor input. It allows you to save energy and money by adapting your heating strategy based on electricity prices, indoor temperature, and weather forecasts.

---

## ✅ Features

- 🔧 AI-based virtual outdoor temperature control
- ⚡ Adjusts heating strategy based on:
  - indoor temperature
  - target temperature
  - electricity price forecast
  - temperature forecast
- 🌡️ Fake outdoor temperature is calculated to trick the heat pump into saving or buffering energy
- 🚀 Pre-boost mode: build up heat buffer before price peaks
- 🧊 Braking mode: avoid heating when it's cold and expensive
- 🏖️ Summer mode: disables fake temperature when outdoor temp is above threshold
- 📊 Fully local (no cloud dependencies)
- 🧠 Self-adjusting inertia calculation
- 🔄 Supports comfort profiles via aggressiveness
- 📈 ApexCharts examples included

---

## 🔧 Installation

1. Place the `pumpsteer` directory in your Home Assistant `custom_components` folder.
2. Restart Home Assistant.
3. Add the integration via **Settings > Devices & Services > Add Integration > PumpSteer**.

---

## 🧱 Required Inputs

| Type          | Description                                      |
|---------------|--------------------------------------------------|
| `sensor`      | Indoor temperature sensor                        |
| `sensor`      | Real outdoor temperature sensor                  |
| `sensor`      | Electricity price sensor (e.g. Nordpool)         |
| `input_text`  | Hourly forecast temperatures (CSV string, 24 values) |
| `input_number`| Target indoor temperature                        |
| `input_number`| Summer mode threshold temperature                |
| `input_number` (optional) | Aggressiveness level (0.0 to 3.0)    |
| `input_number` (optional) | House inertia (or let PumpSteer learn it) |

---

## 🧪 Forecast Format

The input_text must contain **24 comma-separated values** representing hourly forecasted outdoor temperatures:

```text
-3.5,-4.2,-5.0,-4.8,... (24 values total)
```

If the string is invalid or incomplete, the sensor will log a warning and temporarily suspend calculations.

---

## 📊 Sensor Output

`sensor.pumpsteer` provides:

**State:**  
The fake outdoor temperature (`°C`) sent to your heat pump.

**Attributes:**

| Attribute                 | Meaning                                                  |
|--------------------------|-----------------------------------------------------------|
| `status`                 | "OK" or reason for delay (e.g. waiting for data)          |
| `mode`                   | One of: `heating`, `braking`, `neutral`, `summer_mode`, `preboost`, `braking_mode` |
| `real_outdoor_temperature` | From the real outdoor sensor                           |
| `target_temperature`     | Your desired indoor temp                                  |
| `indoor_temperature`     | Current indoor temp                                       |
| `inertia`                | How slowly the house reacts to outdoor temp changes       |
| `aggressiveness`         | From 0.0 (passive) to 3.0 (aggressive saving)             |
| `summer_threshold`       | The outdoor temp threshold to disable heat control        |
| `price_forecast`         | Hourly electricity prices (from Nordpool, Tibber etc.)    |
| `preboost_active`        | True if preboost or braking is active                     |

---

## Aggressiveness – What Does It Do?

Aggressiveness controls how sensitive the system is to electricity prices. It affects both when heating is reduced (braking) and when extra heating is added (pre-boost).

| Setting | Braking behavior     | Pre-boost behavior         |
|---------|----------------------|----------------------------|
| Low     | Rarely brakes        | Boosts more easily         |
| High    | Brakes early         | Boosts only in extreme cases |

**Higher aggressiveness saves energy more aggressively, but may reduce indoor comfort.**

---


## 📈 ApexCharts Example

```yaml
type: custom:apexcharts-card
graph_span: 24h
span: 1h
header:
  title: PumpSteer Strategy
series:
  - entity: sensor.pumpsteer
    name: Fake Outdoor Temp
  - entity: sensor.real_outdoor_temperature
    name: Real Outdoor Temp
  - entity: sensor.indoor_temperature
    name: Indoor Temp
```

---

## 🧠 How It Works

PumpSteer calculates a "fake" outdoor temperature that nudges your heat pump to either:

- Heat earlier when prices are low (preboost)
- Avoid heating when prices are high (braking)
- Maintain comfort with minimal cost using indoor delta + aggressiveness
- Enter summer mode when outdoor temp is high

---

## 💬 Logging and Troubleshooting

- Warnings and errors are logged in Home Assistant.
- If required data is unavailable, PumpSteer will show `unavailable` and try again.
- Inertia is automatically calculated unless overridden via `input_number.house_inertia`.

---

## 🧪 Developer Notes

- Python logic is split into clear modules (`sensor.py`, `pre_boost.py`)
- Easily testable: key functions like `calculate_virtual_temperature` are pure
- Logging is verbose to support debugging and optimization

---

## 🔗 Links

- [Documentation](https://github.com/JohanAlvedal/pumpsteer)
- [Issue Tracker](https://github.com/JohanAlvedal/pumpsteer/issues)

---

## 📄 License

MIT © Johan Älvedal
