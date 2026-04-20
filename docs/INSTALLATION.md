---
layout: default
title: Installation
nav_order: 2
---

# 🚀 Installation Guide
{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Requirements

Before installing, make sure you have:

- **Home Assistant** 2023.12 or later
- A **Nordpool** (or compatible) electricity price sensor with `raw_today` and `raw_tomorrow` attributes
- An **indoor temperature** sensor
- An **outdoor temperature** sensor
- *(Optional)* A **weather entity** — required for forecast-based preheat and precool
- *(Optional)* An **[Ohmigo](https://www.ohmigo.io/)** WiFi controller for direct hardware push

---

## New Installation

### Step 1 — Add via HACS

1. Open HACS in your Home Assistant sidebar.
2. Go to **Integrations** → click the three-dot menu → **Custom repositories**.
3. Add `https://github.com/JohanAlvedal/PumpSteer` as an **Integration**.
4. Search for **PumpSteer** and click **Download**.

### Step 2 — Restart Home Assistant

A full restart is required after installing a new custom integration.

### Step 3 — Add the integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **PumpSteer** and select it.
3. Fill in the required entities:

| Field | Description |
|---|---|
| **Indoor temperature sensor** | Your indoor thermometer sensor |
| **Outdoor temperature sensor** | The real outdoor temperature |
| **Electricity price sensor** | Today's price list (e.g. Nordpool) |
| **Tomorrow price sensor** | Tomorrow's price list |
| **Weather entity** *(optional)* | Used for forecast-based preheat |

### Step 4 — Verify

After setup, check that:

- `sensor.pumpsteer` is active and shows a temperature value
- The `status` attribute reads `ok`
- The `mode` attribute changes sensibly over time (normal → braking → normal)
- The `price_category` attribute reflects current electricity prices

{: .note }
It can take a few minutes after HA startup before all entities report valid states.
PumpSteer falls back to **safe mode** (passing through real outdoor temp) until all
required sensors are available.

---

## Manual Installation

If you prefer not to use HACS:

1. Download the [latest release](https://github.com/JohanAlvedal/PumpSteer/releases) from GitHub.
2. Extract and copy the `custom_components/pumpsteer/` folder to your HA
   `config/custom_components/` directory.
3. Restart Home Assistant.
4. Continue from Step 3 above.

---

## Upgrade from 2.0.x → 2.1.x

{: .highlight }
No migration required. Existing setups continue working without changes.

New in 2.1.x:
- `sensor.pumpsteer_thermal_outlook` is automatically registered
- `switch.pumpsteer_preheat_boost` replaces the options-flow toggle (your saved value is preserved via RestoreEntity)

---

## Upgrade from 1.x → 2.x

{: .warning }
PumpSteer 2.0 is a **complete rewrite**. Treat this as a new integration, not an update.

### Breaking changes

| What changed | Action required |
|---|---|
| Price categories | Old categories (`very_cheap`, `extreme`) are gone. New: `cheap`, `normal`, `expensive` |
| Entity IDs | All entities have been renamed — update dashboards and automations |
| ML features | Removed entirely |
| Options flow | Rebuilt — reconfigure after upgrade |

### Recommended upgrade path

1. Note your current settings (target temp, aggressiveness, etc.)
2. Remove the old PumpSteer integration
3. Install 2.x fresh via HACS
4. Reconfigure with your saved settings
5. Observe for 24–48 hours before migrating dashboards and automations

---

## What PumpSteer creates

After setup, PumpSteer registers the following entities:

### Sensors
| Entity | Description |
|---|---|
| `sensor.pumpsteer` | The fake outdoor temperature sent to the heat pump |
| `sensor.pumpsteer_thermal_outlook` | Forecast analysis (preheat worthwhile, trend, etc.) |

### Number sliders
| Entity | Description | Default |
|---|---|---|
| `number.pumpsteer_target_temperature` | Desired indoor temperature | 21 °C |
| `number.pumpsteer_summer_mode_threshold` | Outdoor temp at which summer mode activates | 17 °C |
| `number.pumpsteer_saving_level` | Aggressiveness 0–5 | 3 |
| `number.pumpsteer_brake_ramp_time` | Ramp duration (house inertia) | 2.0 |

### Switches
| Entity | Description | Default |
|---|---|---|
| `switch.pumpsteer_preheat_boost` | Enable/disable preheat boost | On |
| `switch.pumpsteer_notifications` | Enable/disable price notifications | On |
| `switch.pumpsteer_holiday_mode` | Enable holiday mode (16 °C target) | Off |
| `switch.pumpsteer_ohmigo_enabled` | Enable/disable Ohmigo push | On |

### Datetime helpers
| Entity | Description |
|---|---|
| `datetime.pumpsteer_holiday_start` | Holiday start time (auto-activates holiday mode) |
| `datetime.pumpsteer_holiday_end` | Holiday end time (auto-deactivates holiday mode) |
