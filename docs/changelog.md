## What's New in 2.1.0

PumpSteer 2.1.0 focuses on **observability, diagnostics, and future-ready architecture**.

### 🔍 Thermal Outlook sensor

A new sensor, `sensor.pumpsteer_thermal_outlook`, is now available.

It exposes PumpSteer’s internal forecast analysis, making it easier to understand:

- Whether preheating is worthwhile
- Strength of upcoming cold conditions
- Warming or cooling trends
- Precool risk

This improves transparency and helps explain *why* PumpSteer makes decisions.

> Note: This sensor is primarily diagnostic in 2.1.0 and does not replace the core control logic.

---

### 🎛️ Preheat boost switch

Preheat boost is now available as a switch:

`switch.pumpsteer_preheat_boost`

You can now control it:

- Directly from the dashboard
- From automations

No need to use the options flow anymore.

---

### 🧠 Foundation for smarter control

Internal modules have been refactored:

- `forecast.py` → improved forecast analysis
- `thermal_model.py` → collects real cooling behavior during braking

In 2.1.0, this is used for:

- Diagnostics
- Observability
- Future development

Not yet part of the active control loop.

---

### 🧹 Internal improvements

- Cleaner structure
- Better separation between control and diagnostics
- Improved maintainability

---

### 🔄 Upgrade notes

- No migration required  
- Existing setups continue working  
- New features are optional  

PumpSteer 2.1.0 is fully backward compatible with 2.0.x
---

## [2.0.0]

### Major rewrite
- PI controller
- State machine
- Price classification
