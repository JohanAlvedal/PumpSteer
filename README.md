# 🔥 PumpSteer 2.0.0

➡️ Swedish version: [README (Svenska)](README_sv.md)

> ⚠️ This is a major rewrite. Read upgrade notes before installing.

PumpSteer is a Home Assistant custom integration that optimizes your heat pump by dynamically adjusting the **virtual outdoor temperature**.

It reduces energy cost when electricity is expensive — while protecting indoor comfort.

---

## 📘 Documentation

- [Upgrade Warning](#important--not-a-drop-in-upgrade)
- [What's New](#whats-new-in-200)
- [Breaking Changes](#breaking-changes)
- [Price Sensors](#price-sensor-support)
- [Weather Support](#weather-support)
- [New Installation](#new-installation)
- [Dashboard (Lovelace)](#lovelace-dashboard-mini-graph-card)
- [Upgrade Guide](#upgrade-from-166)
- [Troubleshooting](#troubleshooting)
- [Tuning](#tuning-quick-guide)
- [Safety](#safety--disclaimer)

---

## Important – Not a Drop-in Upgrade ⚠️

PumpSteer 2.0.0 is **not a minor update**.  
It is a **complete rewrite of the control system**.

👉 Treat this as a **new integration**, not an upgrade.

### What this means

- ❌ Old dashboards will not behave the same
- ❌ Automations may break
- ❌ Old helpers are no longer primary
- ❌ Price logic is completely changed

---

### Required after upgrade

- Rebuild Lovelace cards
- Update automations
- Verify price sensors (today + tomorrow)
- Reconnect to new entities
- Retune settings

---

### Behavior is different

- PI control instead of heuristics
- Ramped braking
- Forecast-aware decisions

➡️ Do not expect 1.6.6 behavior

---

### Recommendation

1. Install 2.0.0
2. Observe for 24–48h
3. Then migrate fully

---

## What's New in 2.0.0

- 🧠 PI-based control (replaces heuristics)
- ⚡ Smart price classification (`cheap / normal / expensive`)
- 🔁 State machine (predictable behavior)
- 🧊 Dynamic braking (ramp + hold + filtering)
- 🌦 Forecast-aware planning (optional)
- 🏠 Integration-managed entities
- 🔒 Fully local (no cloud)

---

## Breaking Changes

### Price categories changed

Old:
- `very_cheap`
- `very_expensive`
- `extreme`

New:
- `cheap`
- `normal`
- `expensive`

---

### Price sensor requirements

Must support:
- `today/raw_today`
- `tomorrow/raw_tomorrow`

---

### Control system rewritten

- Old: heuristic logic
- New: PI + state machine

---

### Braking redesigned

- ramping
- hold logic
- peak filtering
- comfort protection

---

### Integration owns entities

- numbers
- switch
- datetime

---

### ML removed

- no longer part of runtime

---

## Price Sensor Support

Supported formats:

- `0.95`
- `"0.95"`
- `{ "value": 0.95 }`
- `{ "price": 0.95 }`

📌 Recommended example:

[`other/nordpool.yaml`](other/nordpool.yaml)

✔ Works with:
- Official Nord Pool integration
- PumpSteer 2.0.0

---

## Weather Support

Examples:
- `weather.smhi_home`
- `weather.yr_home`

⚠️ Must be selected in:  
Settings → Devices → PumpSteer → Configure

---

## New Installation

### Step-by-step

1. Install via HACS or manually
2. Restart Home Assistant
3. Add integration
4. Select required sensors

---

### First validation

- `sensor.pumpsteer` active
- `status = ok`
- `price_category` changes
- `mode` behaves logically

---

## Lovelace Dashboard (mini-graph-card)

📁 See [`/dashboards/`](dashboards/) folder for ready-to-use examples

PumpSteer includes example Lovelace configurations using `mini-graph-card` for visualization.

These dashboards show:
- Indoor temperature
- Target temperature
- Fake outdoor temperature
- Price behavior and system response

---

### ⚠️ Requirement

You must install:

- **mini-graph-card**

Available via HACS:
- Frontend → `mini-graph-card`

---

### 📥 How to use the provided templates

The Lovelace examples in this repository are written as **full YAML cards or views**.

To use them:

1. Go to your Home Assistant dashboard
2. Click **Edit dashboard**
3. Click the **pencil icon (✏️)** on the view/tab you want to edit
4. Click the **three dots (⋮)** in the top right corner
5. Select **Edit dashboard (Raw configuration editor)**
   *(or “Edit in YAML” depending on your HA version)*
6. Paste the provided YAML code
7. Save

⚠️ Note:  
If you paste a full view configuration, it may overwrite the existing view.  
Make sure to back up your dashboard before pasting.

---

### 🧠 Important

- These templates are **not UI cards you click together**
- They must be **pasted as YAML**
- Some templates may replace the entire view
- You may need to adjust entity names to match your setup

---

### 🔧 Common adjustments

After pasting, check:

- `sensor.pumpsteer`
- temperature sensors
- any custom entities

---

### 💡 Tips

- If graph shows no data → check entity IDs
- If card does not load → verify `mini-graph-card` is installed
- Use Developer Tools → States to debug

---

### 📌 Notes

These dashboards are optimized for PumpSteer 2.0.0.

They may not work correctly with older versions (e.g. 1.6.6).

---

## Upgrade from 1.6.6

### Required

- Update price categories
- Configure tomorrow price
- Update automations
- Remove ML

---

### Recommended

- Verify price attributes
- Configure weather entity
- Update holiday automations

---

### Test

- Check `mode`
- Check `brake_factor`
- Observe expensive period

---

## Troubleshooting

### Safe mode

Cause:
- missing price data

Fix:
- check `today/raw_today`
- check `tomorrow/raw_tomorrow`

---

### No braking

Cause:
- not expensive
- comfort protection

---

### Wrong price category

Cause:
- bad data format

---

## Tuning (Quick Guide)

### Aggressiveness

- 0 → no price control
- 1–2 → mild
- 3–4 → balanced
- 5 → aggressive

---

### Inertia

- Low → fast system
- High → slow system

Typical:
- Apartment → low
- House → medium
- Heavy house → high

---

## Safety & Disclaimer

You use this integration at your own risk.

Heating is a critical system.

Do not use if:
- system is unstable
- you don’t understand behavior

Always monitor:
- indoor temperature
- system response

---

## Recorder Requirement

Requires:
- 72 hours of price history
- stored in recorder

If missing:
- classification fails
- safe mode may trigger

---

## Note

This is a hobby project built with:
- ChatGPT
- Copilot
- patience 🙂

Feedback is welcome!

---

## Links

- GitHub repository
- Create Issue

---

## License

- ≥ v1.6.2 → AGPL-3.0
- ≤ v1.5.1 → Apache 2.0

© Johan Älvedal
