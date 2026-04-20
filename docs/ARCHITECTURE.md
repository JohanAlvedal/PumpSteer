---
layout: default
title: Architecture
nav_order: 5
---

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

- **Indoor temperature** — comfort control via PI controller
- **Electricity spot price** — cost optimization via brake and preheat overlays
- **Weather forecast** — anticipation of cold or warm periods

The architecture is **PI-controller centric**. All other signals are overlays on top of
the PI output — never replacements for it.

---

## Core Principles

### 1. PI Controller is the Primary Control Loop

The PI controller is the only feedback loop in the system.

- **Input:** temperature error (`target − indoor`)
- **Output:** heating demand (°C offset applied to outdoor temperature)
- **Integral term:** handles steady-state error (e.g. a cold day requiring sustained heating)

```
fake_temp = outdoor − PI_demand
          + brake_overlay    (raises fake temp during expensive slots)
          + preheat_boost    (lowers fake temp before expensive slots)
```

The PI integral is **frozen** (not decayed, not reset) while braking is active. When
the brake releases, the PI immediately resumes with full context of prior thermal demand —
no lag, no relearning period.

### 2. Feedforward is External and Price/Forecast-Based

Feedforward signals come exclusively from electricity price and weather forecast.

| Signal source | Effect |
|---|---|
| Cheap electricity | Preheat boost — lower fake temp = more heating |
| Expensive electricity | Brake overlay — raise fake temp = less heating |
| Cold forecast + upcoming expensive | Preheat boost to build thermal mass |

Feedforward is applied as a **bounded overlay** on top of PI output.

### 3. Brake is a Bounded, Ramped Overlay

The brake raises the fake outdoor temperature by `BRAKE_DELTA_C` (default 10 °C),
making the heat pump think it is warmer outside and reduce output.

Rules:
- Always smooth — ramped in and out, never a hard step
- `dt` per ramp step is capped at 60 seconds (prevents jumps after HA restarts)
- Released immediately if indoor temperature falls below the comfort floor
- Held briefly after expensive period ends (`BRAKE_HOLD_MINUTES = 30 min`)
- PI integral is **frozen** while brake is active

### 4. No Double Influence

Each signal influences the system once only:

- Price classification drives brake **or** preheat — never both simultaneously
- Pre-brake (5a) is a pure price signal, independent of forecast
- Preheat-boost (5b) is a forecast signal, only active when cold weather is coming

### 5. Simplicity Over Complexity

- No ML, no black-box decisions
- All behavior is explainable from inputs alone
- If a behavior cannot be described simply, it does not belong in the system

---

## State Machine — Priority Order

The control loop evaluates blocks in strict priority order and returns on the first match:

```
1. Summer mode    → outdoor ≥ summer_threshold → passthrough real temp
2. Safe mode      → required sensor missing    → passthrough real temp
3. Aggressiveness 0 → pure PI, all price logic disabled
4. Braking        → current price is expensive AND comfort allows
5a. Pre-brake     → expensive imminent, within ramp_in window
5b. Preheat-boost → expensive imminent AND forecast is cold
6. Normal PI      → default, with optional ramp-out from previous brake
```

---

## Operating Modes

| Mode | Trigger | PI active | Brake active | Integral |
|---|---|---|---|---|
| `summer_mode` | outdoor ≥ summer threshold | No | No | — |
| `safe_mode` | sensor data missing | No | No | — |
| `normal` | default | Yes | No (or ramp-out) | Accumulates |
| `holiday` | holiday switch on | Yes (lower target) | No (or ramp-out) | Accumulates |
| `braking` | price expensive, comfort OK | Frozen¹ | Yes | Frozen |
| `pre_braking` | expensive imminent, within ramp_in | Frozen¹ | Yes (ramping in) | Frozen |
| `preheating` | expensive imminent + cold forecast | Yes + boost | No | Accumulates |

¹ PI is computed with a frozen integral. At `factor = 1.0` the PI output has no effect
on `fake_temp`. It influences output only during ramp-in/ramp-out (`0 < factor < 1`)
as part of the blend.

---

## Price Classification

Prices are classified relative to today's price spread using P30 and P80 percentiles:

| Category | Condition |
|---|---|
| `cheap` | Below P30, or below `ABSOLUTE_CHEAP_LIMIT` (0.50 SEK/kWh) |
| `normal` | Between P30 and P80 |
| `expensive` | Above P80 |

**Thresholds are cached per calendar day.** Recomputing hourly caused mid-slot
reclassification — P80 could shift just enough to flip an ongoing expensive slot to
normal and release the brake unexpectedly. Daily caching keeps thresholds stable.

If P80 for the day is below `ABSOLUTE_CHEAP_LIMIT`, all slots are classified as cheap
(no braking occurs on universally cheap days).

{: .note }
`HISTORY_WEIGHT` / `HORIZON_WEIGHT` and `compute_price_thresholds()` (72-hour trailing
history) exist in `settings.py` / `electricity_price.py` but are not applied.
Reserved for a future hybrid implementation.

---

## Brake Ramp Mechanics

```python
# Ramp factor update (each polling cycle, ~60s)
factor += dt_s / (ramp_in_min × 60)     # while brake requested
factor -= dt_s / (ramp_out_min × 60)    # while not requested and hold expired
dt_s = min(actual_dt, 60)               # cap prevents jumps after restarts
factor = clamp(factor, 0.0, 1.0)

# Output blend
fake_temp = pi_fake + (brake_temp − pi_fake) × factor
brake_temp = outdoor + BRAKE_DELTA_C
```

At `factor = 0.0`: pure PI output (no brake).
At `factor = 1.0`: full brake (PI frozen, brake temp dominates).

Ramp timing from house inertia slider:

```
ramp_in  = clamp(house_inertia × 10, 20 min, 60 min)
ramp_out = clamp(ramp_in × 0.8, 20 min, 60 min)   # ramp-out is 20% faster than ramp-in
```

---

## Pre-brake vs Preheat-boost

These two blocks are distinct and are often confused:

### Pre-brake (block 5a) — pure price signal

- Triggers when expensive period is within `ramp_in` minutes
- Starts ramp so brake reaches full factor exactly when the slot starts
- **No forecast dependency** — brakes regardless of weather
- Mode: `pre_braking`

### Preheat-boost (block 5b) — forecast signal

- Triggers when expensive period is coming **AND** a simple cold-forecast heuristic (`_forecast_is_cold()`) returns true
- Adds `PREHEAT_BOOST_C = 4 °C` boost to PI demand
- Only active when cold — pointless in warm weather
- Suppressed when indoor temperature is already at or above target
- Requires `switch.pumpsteer_preheat_boost` to be on
- Mode: `preheating`

{: .note }
`sensor.pumpsteer_thermal_outlook` provides richer forecast analysis but does **not**
yet control block 5b. Preheat decisions in 2.1.x are still made by the simple
`_forecast_is_cold()` heuristic. Connecting `ThermalOutlook.preheat_worthwhile` to
block 5b is the next planned step.

{: .important }
Block 5a must never be forecast-gated. If forecast data is unavailable, the brake must
still engage before the expensive slot. Forecast availability cannot be a dependency
for price-based braking.

---

## Comfort Floor

The brake releases immediately when indoor temperature falls below the comfort floor,
regardless of price or hold time:

```
comfort_floor = target − COMFORT_FLOOR_BY_AGGRESSIVENESS[aggressiveness]
```

| Aggressiveness | Allowed drop | Comfort floor (target = 21 °C) |
|---|---|---|
| 0 | 0 °C | 21.0 °C (PI only, no price logic) |
| 1 | 0.5 °C | 20.5 °C |
| 2 | 1.0 °C | 20.0 °C |
| 3 | 1.5 °C | 19.5 °C *(default)* |
| 4 | 2.0 °C | 19.0 °C |
| 5 | 3.0 °C | 18.0 °C |

When the comfort floor triggers, `brake_hold` is set to 0 and the brake releases
immediately. No hold time is applied.

---

## Summer Mode

When outdoor temperature reaches or exceeds `summer_threshold` (default 17 °C):

- All control logic is bypassed
- Real outdoor temperature is passed through unchanged
- PI is reset, brake ramp is cleared
- Heat pump operates on its own summer logic

Summer mode is the **highest-priority check** — it short-circuits everything else.

---

## Safe Mode

When any required sensor is missing or invalid:

- Real outdoor temperature is passed through unchanged
- PI is reset, brake ramp is cleared
- `status` attribute contains the specific failure reason
- Resolves automatically when valid data returns

---

## Thermal Outlook (2.1.0+)

{: .warning }
`sensor.pumpsteer_thermal_outlook` is **diagnostic only** in 2.1.x. It does not
influence any control decisions. Preheat is still controlled by the simple
`_forecast_is_cold()` heuristic — not by this sensor.

`sensor.pumpsteer_thermal_outlook` exposes the result of `analyze_thermal_outlook()`,
which analyzes the 24-hour weather forecast to determine:

| Attribute | Description |
|---|---|
| `preheat_worthwhile` | True if cold enough, long enough, and no warm day incoming |
| `preheat_strength` | 0.0–1.0, scales with how cold the forecast is |
| `warming_trend` | Temperature rising in the next 6 hours |
| `cooling_trend` | Temperature falling in the next 6 hours |
| `precool_risk` | Warm period coming that will heat the house naturally |
| `night_min_temp` | Lowest forecast temp in 22:00–06:00 window |
| `day_max_temp` | Highest forecast temp in 06:00–22:00 window |

Connecting `ThermalOutlook.preheat_worthwhile` to block 5b is the next planned step.
See the [Roadmap](ROADMAP) for details.

---

## What is Out of Scope

- Machine learning control loops
- Self-modifying parameters
- Black-box optimization
- Any behavior that cannot be explained from its inputs alone
- Cloud dependencies
