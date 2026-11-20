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

- **Home Assistant** 2024.4 or later
- A **Nordpool** (or compatible) electricity price source with `today` / `raw_today` and `tomorrow` / `raw_tomorrow` price lists
- An **indoor temperature** sensor
- An **outdoor temperature** sensor
- *(Optional)* A **weather entity** — required for forecast-based preheat and precool
- *(Optional)* An **[Ohmigo](https://www.ohmigo.io/)** WiFi controller for direct hardware push

---

## New Installation

### Step 1 — Install PumpSteer

[![Open your Home Assistant instance and open PumpSteer in HACS / the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JohanAlvedal&repository=PumpSteer&category=integration)

The button opens PumpSteer in HACS on Home Assistant 2026.10 or older, and in the
Marketplace on Home Assistant 2026.11 or newer.

**Home Assistant 2026.11 or newer (Marketplace)**

1. Go to **Settings** → **Marketplace**.
2. Search for **PumpSteer**.
3. Select PumpSteer and click **Download**.

**Home Assistant 2026.10 or older (HACS)**

1. Open HACS in your Home Assistant sidebar.
2. Go to **Integrations**.
3. Search for **PumpSteer**.
4. Select PumpSteer and click **Download**.

{: .note }
PumpSteer is in the default catalog used by both HACS and the Marketplace. You do not
need to add it as a custom repository.

{: .note }
Upgrading Home Assistant to 2026.11 or newer replaces HACS with the built-in
Marketplace automatically. An existing PumpSteer installation stays installed, keeps
its configuration and entity IDs, and keeps receiving updates. No action is needed.

### Step 2 — Restart Home Assistant

A full restart is required after installing a new custom integration.

### Step 3 — Add the integration
Go to Settings → Devices & Services → Add Integration.
Search for PumpSteer and select it.
Fill in the required entities:

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
required sensors are available. Temperature sensors that only report when their value
changes are accepted at the latest 5 minutes after HA has started.

### Step 5 — Optional: enable the sidebar panel

Go to **Settings → Devices & Services → PumpSteer → Configure** and turn on
**Show PumpSteer panel in the sidebar**. See [Dashboard Setup](DASHBOARD) for what
the panel shows.

---

## Manual Installation

If you prefer not to use HACS or the Marketplace:

1. Download the [latest release](https://github.com/JohanAlvedal/PumpSteer/releases) from GitHub.
2. Extract and copy the `custom_components/pumpsteer/` folder to your HA
   `config/custom_components/` directory.
3. Restart Home Assistant.
4. Continue from Step 3 above.

---

## Updating PumpSteer

Update from HACS or the Marketplace when a new release is offered, then restart
Home Assistant. Settings and entity IDs are kept. Release-specific notes are in
the [Changelog](CHANGELOG).

---

## What PumpSteer creates

After setup, PumpSteer registers the following entities.

{: .note }
The entity IDs below are the ones created on a new installation. Installations first
set up with an older PumpSteer version keep their original entity IDs (for example
`number.pumpsteer_house_inertia` for Brake Ramp Time). Check
**Settings → Devices & Services → PumpSteer** for the IDs in your installation.

### Sensors
| Entity | Description |
|---|---|
| `sensor.pumpsteer` | The fake outdoor temperature plus control diagnostics such as mode, current price, brake factor and ThermalModel state |
| `sensor.pumpsteer_thermal_outlook` | Forecast analysis: `preheat`, `precool` or `idle` |
| `sensor.pumpsteer_indoor_temperature` | The validated indoor temperature PumpSteer uses for control (read-only) |
| `sensor.pumpsteer_outdoor_temperature` | The validated real outdoor temperature PumpSteer uses for control (read-only) |
| `sensor.pumpsteer_estimated_savings` | **Beta.** Estimated value of shifting heat between price periods; never affects control |

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
| `switch.pumpsteer_holiday_mode` | Enable holiday mode (17 °C target) | Off |
| `switch.pumpsteer_ohmigo_push` | Enable/disable Ohmigo push | On |
| `switch.pumpsteer_ohmigo_relay_guard` | Optional Active/Bypass relay recovery guard; created only when a relay is configured | Off on first creation |

### Datetime helpers
| Entity | Description |
|---|---|
| `datetime.pumpsteer_holiday_start` | Holiday start time (auto-activates holiday mode) |
| `datetime.pumpsteer_holiday_end` | Holiday end time (auto-deactivates holiday mode) |
