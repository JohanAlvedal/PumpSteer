---
layout: home
title: PumpSteer
nav_order: 1
---

# 🔥 PumpSteer
{: .fs-9 }

Smart heat pump optimization for Home Assistant.
{: .fs-6 .fw-300 }

[Get Started](docs/INSTALLATION){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/JohanAlvedal/PumpSteer){: .btn .fs-5 .mb-4 .mb-md-0 }

---

PumpSteer is a Home Assistant custom integration that saves money on electricity by
dynamically adjusting the **virtual outdoor temperature** sent to your heat pump
controller — without any cloud dependency, machine learning, or black-box logic.

Everything PumpSteer does is explainable directly from its inputs.

---

## How it works

Your heat pump has a heating curve: the colder it thinks it is outside, the harder it
heats. PumpSteer sits between your outdoor sensor and the heat pump controller and
sends a calculated **fake outdoor temperature** instead of the real one.

By raising the fake temperature during expensive electricity slots, the heat pump
reduces output and saves money. By lowering it before expensive periods, the house
pre-heats while electricity is still cheap.

A **PI controller** maintains indoor comfort at all times. Price and forecast signals
are overlays on top of the PI output — never replacements for it.

```
fake_outdoor_temp = PI_output + brake_overlay + preheat_boost
```

---

## Key features

| Feature | Description |
|---|---|
| **PI control** | Maintains indoor temperature at your target regardless of weather |
| **Price braking** | Reduces heating during expensive electricity slots (P80 threshold) |
| **Pre-brake** | Starts brake ramp before the expensive slot begins |
| **Preheat boost** | Heats extra before expensive periods when forecast is cold |
| **Comfort floor** | Brake releases automatically if indoor temp drops too far |
| **Summer mode** | Passes through real outdoor temp when it is warm enough |
| **Ohmigo support** | Pushes fake temp directly to Ohmigo WiFi controller |
| **Holiday mode** | Lowers target to 16 °C during absence |
| **Fully local** | No cloud, no API keys, no ML |

---

## Operating modes

| Mode | What triggers it |
|---|---|
| `normal` | Default PI control |
| `braking` | Current price slot is expensive |
| `pre_braking` | Expensive slot is imminent (within ramp window) |
| `preheating` | Expensive slot is imminent AND forecast is cold |
| `summer_mode` | Outdoor temp ≥ summer threshold |
| `safe_mode` | Required sensor data is missing |
| `holiday` | Holiday mode switch is on |

---

## Requirements

- Home Assistant 2023.12 or later
- A Nordpool (or compatible) electricity price sensor with `raw_today` / `raw_tomorrow` attributes
- An indoor temperature sensor
- An outdoor temperature sensor
- *(Optional)* A weather entity for forecast-based preheat
- *(Optional)* An [Ohmigo](https://www.ohmigo.io/) device for direct hardware push

---

## Documentation

| | |
|---|---|
| 🚀 [Installation Guide](docs/INSTALLATION) | Step-by-step setup |
| ⚙️ [Configuration](docs/Configuration) | All settings explained |
| 📊 [Dashboard Setup](docs/DASHBOARD) | Lovelace cards and templates |
| 🧠 [Architecture](docs/ARCHITECTURE) | How the PI control and state machine works |
| 🔧 [Tuning Guide](docs/TUNING) | Optimize for your home |
| 🛠 [Troubleshooting](docs/TROUBLESHOOTING) | Common problems and fixes |
| 📋 [Changelog](docs/CHANGELOG) | Version history |
| 🗺 [Roadmap](docs/ROADMAP) | Planned features |
| ⚖️ [Design Decisions](docs/DECISIONS) | Why things work the way they do |

---

{: .warning }
**Disclaimer:** Heating is a critical system. Use PumpSteer at your own risk. Always
monitor behavior after installation and ensure your fallback (safe mode) works correctly.

---

<a href="https://www.buymeacoffee.com/alvjo" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px; width: 200px;">
</a>
