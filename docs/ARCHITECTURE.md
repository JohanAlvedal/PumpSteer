---

layout: default
title: Architecture
nav_order: 5
------------

# 🧠 System Architecture

{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Overview

PumpSteer optimizes heat pump behavior by manipulating the perceived outdoor temperature
— a "fake outdoor temperature" sent to the heat pump controller. The heat pump's own
heating curve does the rest.

The system calculates the fake temperature based on:

* **Indoor temperature** — comfort control via PI controller
* **Electricity spot price** — cost optimization via brake and preheat overlays
* **Weather forecast** — anticipation of cold or warm periods

The architecture is **PI-controller centric**. All other signals are overlays on top of
the PI output — never replacements for it.

---

## Core Principles

### 1. PI Controller is the Primary Control Loop

The PI controller is the only feedback loop in the system.

* **Input:** temperature error (`target − indoor`)
* **Output:** heating demand (°C offset applied to outdoor temperature)
* **Integral term:** handles steady-state error

```
fake_temp = outdoor − PI_demand
          + brake_overlay
          + preheat_boost
```

👉 **Important:**
The PI controller is always active.
Price and forecast logic only modify the output — they never replace it.

---

### 2. Feedforward is External and Price/Forecast-Based

Feedforward signals come exclusively from electricity price and weather forecast.

| Signal source         | Effect                                   |
| --------------------- | ---------------------------------------- |
| Cheap electricity     | Preheat boost — more heating             |
| Expensive electricity | Brake overlay — less heating             |
| Cold forecast         | Enables preheat before expensive periods |

Feedforward is applied as a **bounded overlay** on top of PI output.

---

### 3. Brake is a Bounded, Ramped Overlay

The brake raises the fake outdoor temperature by `BRAKE_DELTA_C` (default 10 °C),
making the heat pump think it is warmer outside and reduce output.

Rules:

* Always smooth — ramped in and out, never a hard step
* `dt` per ramp step is capped at 60 seconds
* Released immediately if indoor temperature falls below the comfort floor
* Held briefly after expensive period ends (`BRAKE_HOLD_MINUTES`)
* PI integral is **frozen** while brake is active

---

### 4. No Double Influence

Each signal influences the system once only:

* Price classification drives brake **or** preheat — never both simultaneously
* Pre-brake (5a) is a pure price signal
* Preheat-boost (5b) is a forecast signal

---

### 5. Simplicity Over Complexity

* No ML, no black-box decisions
* All behavior is explainable
* If it can’t be explained simply, it doesn’t belong

---

## State Machine — Priority Order

The control loop evaluates blocks in strict priority order:

```
1. Summer mode
2. Safe mode
3. Aggressiveness 0 → pure PI
4. Braking
5a. Pre-brake
5b. Preheat
6. Normal PI
```

---

## Operating Modes

| Mode        | Trigger                | PI active | Brake active | Integral    |
| ----------- | ---------------------- | --------- | ------------ | ----------- |
| summer_mode | outdoor ≥ threshold    | No        | No           | —           |
| safe_mode   | sensor missing         | No        | No           | —           |
| normal      | default                | Yes       | No           | Accumulates |
| holiday     | holiday active         | Yes       | No           | Accumulates |
| braking     | expensive price        | Frozen    | Yes          | Frozen      |
| pre_braking | expensive imminent     | Frozen    | Ramping      | Frozen      |
| preheating  | cold + expensive ahead | Yes       | No           | Accumulates |

---

## Price Classification

Prices are classified using **today’s price spread only**:

| Category  | Condition           |
| --------- | ------------------- |
| cheap     | Below P30           |
| normal    | Between P30 and P80 |
| expensive | Above P80           |

👉 Thresholds are cached per calendar day
👉 They do not change during the day

No historical or hybrid weighting is currently used.

---

## Brake Ramp Mechanics

```
factor += dt_s / (ramp_in × 60)
factor -= dt_s / (ramp_out × 60)
dt_s = min(actual_dt, 60)
factor = clamp(factor, 0.0, 1.0)

fake_temp = pi_fake + (brake_temp − pi_fake) × factor
```

Where:

```
ramp_in  = clamp(house_inertia × 10, 20 min, 60 min)
ramp_out = clamp(ramp_in × 0.8, 20 min, 60 min)
```

👉 This creates smooth transitions between PI and braking.

---

## Pre-brake vs Preheat

### Pre-brake (5a) — price signal

* Trigger: expensive period within ramp window
* No forecast dependency
* Ensures full brake at start

---

### Preheat (5b) — forecast signal

* Trigger: expensive period + cold forecast
* Adds fixed boost (`PREHEAT_BOOST_C`)
* Uses simple heuristic

👉 Important:

* Not dynamically optimized
* Not based on ThermalOutlook yet

Preheat is suppressed when:

* indoor temperature ≥ target

---

## Comfort Floor

```
comfort_floor = target − allowed_drop
```

If:

```
indoor < comfort_floor
```

👉 Brake is released immediately (no hold)

---

## Summer Mode

When outdoor ≥ threshold:

* All control logic is bypassed
* Real temperature is passed through
* PI and brake reset

---

## Safe Mode

When required sensors are missing:

* Real temperature is passed through
* System pauses safely
* Automatically recovers

---

## Thermal Outlook (2.1.0+)

`sensor.pumpsteer_thermal_outlook`

Provides:

* preheat_worthwhile
* preheat_strength
* trends
* risk indicators

👉 Important:

* Diagnostic only in 2.1.0
* Does NOT affect control logic yet

---

## What is Out of Scope

* Machine learning control
* Black-box logic
* Cloud dependencies
* Self-modifying systems
