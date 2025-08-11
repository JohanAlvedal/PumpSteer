# PumpSteer

PumpSteer is a custom Home Assistant integration that dynamically optimizes your heat pump by manipulating the outdoor temperature sensor input. It helps save energy and money by adjusting your heating strategy based on electricity prices, indoor temperature, weather forecasts, and thermal inertia.

<a href="https://www.buymeacoffee.com/alvjo" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;">
</a>

---

## ⚠️ Disclaimer 

I'm not an expert in programming, energy systems, or automation. This setup is based on personal experiments and use. I cannot guarantee it will work for everyone, and I take no responsibility for any issues or damage resulting from the use of this configuration or code.

**Use at your own risk and thoroughly test it in your environment.**

---

## ✅ Features

* 🔧 Smart virtual control of outdoor temperature
* 🌡️ Dynamic comfort control using:

  * Indoor temperature
  * Target indoor temperature
  * Electricity price forecast
  * Temperature forecast (comma-separated list)
  * Thermal inertia
* 💸 Electricity price adjustment via Nordpool or other sensor
* 🧊 Braking mode: limits heating during high prices
* ☀️ Summer mode: disables heating control during warm weather
* 🏝️ Holiday mode: temporarily reduces temperature when away
* 🤖 ML analysis: learns how your house responds (session-based)
* 🔁 Auto-adjustment of `house_inertia` (if enabled)
* 🧠 Recommendations for improved comfort/savings balance
* 🎛️ Fine-tuning via `input_number`, `input_text`, `input_boolean`, `input_datetime`
* 🖼️ Extra sensors for UI visualization

> 💡 **Note:** Holiday mode is only active when the outdoor temperature is below the summer threshold.

---

## 🔧 Installation via HACS (Custom Repository)

If PumpSteer is not yet available in HACS:

1. Go to **HACS > ⋮ > Custom Repositories**
2. Add: `https://github.com/JohanAlvedal/PumpSteer`
3. Choose **Integration** as category
4. Install PumpSteer
5. Restart Home Assistant
6. Follow the setup guide and select helper entities

**For a complete step-by-step installation guide, including setting up helper entities and automations, please refer to our wiki:**

[**PumpSteer - Installation och Grundkonfiguration**](https://github.com/JohanAlvedal/PumpSteer/wiki/PumpSteer-%E2%80%90-Installation-och-Grundkonfiguration)

---

## 📦 Helper Entities (via `pumpsteer_package.yaml`)

| Type             | Entity                          | Function                                |
| ---------------- | ------------------------------- | --------------------------------------- |
| `input_number`   | `indoor_target_temperature`     | Target indoor temperature               |
| `input_number`   | `pumpsteer_summer_threshold`    | Threshold to activate summer mode       |
| `input_number`   | `pumpsteer_aggressiveness`      | Comfort vs savings (0–5)                |
| `input_number`   | `house_inertia`                 | How slow/fast the house responds (0–10) |
| `input_text`     | `hourly_forecast_temperatures`  | Temperature forecast (24 CSV values)    |
| `input_boolean`  | `holiday_mode`                  | Activates holiday mode                  |
| `input_boolean`  | `autotune_inertia`              | Allow system to adjust `house_inertia`  |
| `input_datetime` | `holiday_start` / `holiday_end` | Automatically enable holiday mode       |

---

## 🧪 Forecast Format

`input_text.hourly_forecast_temperatures` must contain exactly 24 comma-separated temperature values (°C):

```
-3.5,-4.2,-5.0,-4.8,… (total 24 values)
```

If the format is invalid, an error will be logged and the forecast ignored.

---

## 📊 Sensor: `sensor.pumpsteer`

This sensor is the main output of the integration.

### State:

Virtual (fake) outdoor temperature sent to your heat pump.

### Attributes:

| Attribute                    | Meaning                                             |
| ---------------------------- | --------------------------------------------------- |
| `Mode`                       | `heating`, `neutral`, `braking_mode`, `summer_mode` |
| `Fake Outdoor Temperature`   | Calculated temperature sent to the heat pump        |
| `Price Category`             | Classification of current electricity price         |
| `Status`                     | System status, e.g. "OK" or error messages          |
| `Current Price`              | Current electricity price in SEK/kWh                |
| `Max Price`                  | Highest price of the day                            |
| `Aggressiveness`             | Comfort vs savings (0–5)                            |
| `Inertia`                    | Estimated house inertia                             |
| `Target Temperature`         | Desired indoor temperature                          |
| `Indoor Temperature`         | Current indoor temperature                          |
| `Outdoor Temperature`        | Real outdoor temperature                            |
| `Summer Threshold`           | Threshold for summer mode                           |
| `Braking Threshold (%)`      | Percent threshold to trigger braking                |
| `Price Factor (%)`           | Position of current price within daily range (0% = min, 100% = max) |
| `Holiday Mode`               | Whether holiday mode is active                      |
| `Last Updated`               | Last update timestamp                               |
| `Temp Error (°C)`            | Deviation from target indoor temperature            |
| `To Summer Threshold (°C)`   | Distance to triggering summer mode                  |
| `Next 3 Hours Prices`        | Upcoming electricity prices                         |
| `Saving Potential (SEK/kWh)` | Potential savings from current price                |
| `Decision Reason`            | Reason for current decision                         |
| `Price Categories All Hours` | Classification for all hours                        |
| `Current Hour`               | Current hour of the day                             |
| `Data Quality`               | Availability and completeness of input data         |

---

## 🧠 Sensor: `sensor.pumpsteer_ml_analysis`

ML sensor showing analysis and recommendations based on your house's behavior.

### Attributes:

| Attribute                  | Description                                         |
| -------------------------- | --------------------------------------------------- |
| `success_rate`             | How often the system reached the target temperature |
| `avg_heating_duration`     | Average heating session duration (min)              |
| `most_used_aggressiveness` | Most used aggressiveness level                      |
| `total_heating_sessions`   | Total number of sessions                            |
| `recommendations`          | Text suggestions based on system performance        |
| `auto_tune_active`         | If automatic inertia adjustment is active           |
| `last_updated`             | Last analysis update timestamp                      |

Recommendations can be shown in UI or in markdown cards.

---

## 🧠 How it works

PumpSteer controls your heat pump's perceived demand using a fake outdoor temperature:

* Increases heating when electricity is cheap
* Avoids heating when prices are high
* Goes to neutral mode when stable
* Disables heating when it's warm outside (summer mode)
* Lowers target temp to 16 °C during holidays
* Learns over time how your house reacts and adjusts settings (if `autotune_inertia` is enabled)

All control is done locally without any cloud dependency.

---

## 🛠️ Logging

* Errors and warnings are logged in Home Assistant
* Sensor shows `unavailable` when data is missing
* ML data is stored in `pumpsteer_ml_data.json` (max 100 sessions)
* Auto-tuned `inertia` is saved in `adaptive_state.json`

---

## 🧪 Note

This is a hobby project built with the help of ChatGPT, Copilot, and a lot of patience. Feedback and improvement ideas are always welcome.

---

## 🔗 Links

* 🔗 [GitHub repo](https://github.com/JohanAlvedal/PumpSteer)
* 🐞 [Create Issue](https://github.com/JohanAlvedal/PumpSteer/issues)

---

© Johan Älvedal
