---
layout: home
title: PumpSteer
nav_order: 1
---

# 🔥 PumpSteer
{: .fs-9 }

Smart heat pump optimization for Home Assistant.
{: .fs-6 .fw-300 }

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
| **Pre-brake** | Starts brake ramp before the expensive slot begins, while comfort allows |
| **Preheat boost** | Builds bounded thermal reserve before expensive periods when the forecast supports it |
| **Thermal headroom** | Saving level limits how far preheat may charge above target |
| **Comfort floor** | Brake and pre-brake release automatically if indoor temp drops too far |
| **Brake hold** | Bridges only short gaps between nearby expensive periods without ramp oscillation |
| **Summer / precool** | Pass-through in summer plus forecast-based warm-period protection |
| **Ohmigo support** | Pushes fake temp directly to Ohmigo WiFi controller |
| **Ohmigo Relay Guard** | Optional recovery of a configured Active/Bypass relay, outside the control loop |
| **Generic Output System** | Optional service-based output to Modbus, MQTT, ESPHome and other HA targets |
| **Holiday mode** | Lowers target to 16 °C during absence |
| **Fully local** | No cloud dependency and no black-box control loop |

## Documentation

- [Generic Output System (GOS)]({{ site.baseurl }}/GOS.html)
- [GitHub Repository](https://github.com/JohanAlvedal/PumpSteer)

---

## Operating modes

| Mode | What triggers it |
|---|---|
| `normal` | Default PI control |
| `braking` | Current price slot is expensive and comfort allows braking |
| `brake_hold` | Existing brake factor is held across a short gap before another expensive period |
| `pre_braking` | Expensive slot is imminent, within ramp window, and comfort allows |
| `preheating` | Expensive period is imminent, forecast supports preheat, and thermal headroom remains |
| `precool` | Warm-period risk triggers a temporary protective brake ramp |
| `summer_mode` | Outdoor temp ≥ summer threshold |
| `safe_mode` | Required temperature or price input is missing/invalid |
| `holiday` | Holiday target is active during otherwise normal PI operation |

---

## Requirements

- Home Assistant 2023.12 or later
- A Nordpool (or compatible) electricity price source exposing `today` / `raw_today` and `tomorrow` / `raw_tomorrow` price lists
- An indoor temperature sensor
- An outdoor temperature sensor
- *(Optional)* A weather entity for forecast-based preheat
- *(Optional)* An [Ohmigo](https://www.ohmigo.io/) device for direct hardware push

---

{: .warning }
**Disclaimer:** Heating is a critical system. Use PumpSteer at your own risk. Always
monitor behavior after installation and ensure your fallback (safe mode) works correctly.

---

<a href="https://www.buymeacoffee.com/alvjo" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px; width: 200px;">
</a>
