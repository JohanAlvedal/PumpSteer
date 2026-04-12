# PumpSteer Architecture

## Overview

PumpSteer is a Home Assistant custom integration that optimizes heat pump behavior by
manipulating the perceived outdoor temperature — a "fake outdoor temperature" sent to
the heat pump controller. The heat pump's own heating curve does the rest.

The system calculates the fake temperature based on:

- Indoor temperature (comfort control via PI controller)
- Electricity spot price (cost optimization via brake and preheat)
- Weather forecast (anticipation of cold periods)

The architecture is **PI-controller centric**. All other signals are overlays on top of
the PI output — never replacements for it.

---

## Core Principles

### 1. PI Controller is the Primary Control Loop

The PI controller is the only feedback loop in the system.

- Input: temperature error (`target − indoor`)
- Output: heating demand (°C offset applied to outdoor temperature)
- Integral term handles steady-state error (e.g. a cold day that needs sustained heating)

The PI controller must:
- Be stable and avoid oscillation
- Have integral windup protection (clamp)
- Freeze its integral during braking — **not decay, not reset**

**Why freeze and not decay/reset during braking:**
The house loses heat while the brake is active, especially in cold weather. When the
brake releases, the PI needs to know how much it was heating before — a frozen integral
preserves that context. Decaying or resetting would cause the PI to underestimate demand
and produce an unnecessary lag before comfort is restored.

---

### 2. Feedforward is External and Price/Forecast-Based

Feedforward signals are derived from electricity price and weather forecast — never from
the temperature error itself.

- Cheap electricity → preheat boost (lower fake temp = more heating)
- Expensive electricity → brake overlay (raise fake temp = less heating)
- Cold forecast → preheat boost when expensive period is approaching

Feedforward is applied as a bounded overlay on top of PI output, not as a replacement.

---

### 3. Brake is a Bounded, Ramped Overlay

The brake raises the fake outdoor temperature by `BRAKE_DELTA_C` (default 10°C), making
the heat pump think it is warmer outside and reduce output accordingly.

Rules:
- Always smooth — ramped in and out, never a hard step
- `dt` per ramp step is capped at 60 seconds to prevent large jumps after HA restarts
  or long gaps between polling cycles
- Released immediately if indoor temperature falls below the comfort floor
- Held briefly after the expensive period ends (`BRAKE_HOLD_MINUTES`) to avoid rapid
  cycling over short cheap dips within a longer expensive block
- The PI integral is **frozen** (not decayed) while the brake is active

---

### 4. No Double Influence

Each signal influences the system once only.

- Price classification drives brake OR preheat — not both simultaneously
- Pre-brake (block 5a) is a pure price signal, independent of forecast
- Preheat-boost (block 5b) is a forecast signal, only active when cold weather is coming

---

### 5. Priority Order (State Machine)

The control loop evaluates blocks in strict priority order and returns early:

1. **Summer mode** — outdoor ≥ summer threshold → passthrough real outdoor temp, no control
2. **Safe mode** — required sensor data missing → passthrough real outdoor temp
3. **Aggressiveness = 0** — pure PI, all price logic bypassed
4. **Braking** — current price is expensive AND comfort allows → brake ramp active
5. **Pre-brake** (5a) — expensive period imminent, within `ramp_in` minutes → start brake ramp
6. **Preheat-boost** (5b) — expensive period imminent AND forecast is cold → boost heating
7. **Normal PI** — default, with optional brake ramp-out if still decaying from a previous brake

---

### 6. Simplicity Over Complexity

- No ML, no black-box decisions
- All behavior must be explainable from inputs alone
- If a behavior cannot be described simply, it does not belong in the system

---

## Operating Modes

| Mode | Trigger | PI active | Brake active | Integral |
|---|---|---|---|---|
| `summer_mode` | outdoor ≥ summer threshold | No | No | — |
| `safe_mode` | sensor data missing | No | No | — |
| `normal` / `holiday` | default | Yes | No (or ramp-out) | Accumulates |
| `braking` | price expensive, comfort OK | Computed¹ | Yes | Frozen |
| `pre_braking` | expensive imminent, within ramp_in | Computed¹ | Yes (ramping in) | Frozen |
| `preheating` | expensive imminent + cold forecast | Yes + boost | No | Accumulates |

¹ PI is computed and the integral is frozen, but at `factor = 1.0` the PI output has
no effect on `fake_temp`. It only influences the output during ramp-in/ramp-out
(`0 < factor < 1`) as part of the blend: `pi_fake + (brake_temp − pi_fake) × factor`.

**Holiday mode** uses a lower target temperature (`HOLIDAY_TEMP = 16°C`) but otherwise
follows the same PI and braking logic as normal mode.

---

## Price Classification

Prices are classified into three categories using hybrid percentile thresholds:

- `cheap` — below P30 (or below absolute limit of 0.50 kr/kWh regardless of history)
- `normal` — between P30 and P80
- `expensive` — above P80

Thresholds are computed from today's known prices only. This matches how Ngenic/Tibber classify prices — relative to the current day's price spread rather than a trailing history window.
If today's prices are not yet available, the combined today+tomorrow list is used as a temporary fallback until the cache can be committed.
HISTORY_WEIGHT / HORIZON_WEIGHT and compute_price_thresholds() (which uses 72-hour trailing history) exist in settings.py / electricity_price.py but are not applied — reserved for a future hybrid implementation.
Thresholds are cached per calendar day.

`HISTORY_WEIGHT` / `HORIZON_WEIGHT` exist in `settings.py` but are not yet applied in
the threshold calculation — they are reserved for a future hybrid implementation.

**Thresholds are cached per calendar day.** Recomputing every hour caused mid-slot
reclassification — P80 could shift just enough to flip an ongoing expensive slot to
normal and release the brake unexpectedly. Caching per day means thresholds are stable
throughout the day and only refresh when new price data arrives at midnight.

---

## Brake Ramp Mechanics

```
factor += dt_s / (ramp_in_min × 60)     # while brake requested
factor -= dt_s / (ramp_out_min × 60)    # while not requested and hold expired
dt_s = min(actual_dt, 60)               # cap prevents jumps after restarts
factor = clamp(factor, 0.0, 1.0)

fake_temp = pi_fake + (brake_temp − pi_fake) × factor
brake_temp = outdoor + BRAKE_DELTA_C
```

At `factor = 0`: pure PI output.
At `factor = 1`: full brake (PI integral still frozen, P-term still computed but overridden).

Ramp timing is derived from `house_inertia` and `RAMP_SCALE`:
```
ramp_in  = clamp(house_inertia × RAMP_SCALE, RAMP_MIN, RAMP_MAX)   # 20–60 min
ramp_out = clamp(ramp_in × 0.5, RAMP_MIN, RAMP_MAX)
```

This means `number.pumpsteer_house_thermal_mass` affects **when pre-brake must begin**.
A higher thermal-mass / house-inertia value produces a longer `ramp_in`, so PumpSteer
starts the brake earlier before an expensive slot. A lower value shortens `ramp_in`,
so pre-brake starts later. The value affects the **timing and shape** of the brake
ramp — not whether price braking is allowed in the first place.

---

## Pre-brake vs Preheat-boost

These are two distinct behaviors that are often confused:

**Pre-brake (block 5a) — pure price signal**
- Triggers when an expensive period is within `ramp_in` minutes
- Starts ramping the brake in *before* the expensive slot begins, so the brake is
  already at full factor when the slot starts
- The `ramp_in` duration comes from `house_inertia`, so a more thermally sluggish house
  starts pre-braking earlier than a fast-reacting house
- Completely independent of weather forecast — if price is going expensive, we brake
  regardless of outdoor temperature
- Mode: `pre_braking`

**Preheat-boost (block 5b) — forecast signal**
- Triggers when an expensive period is coming AND the weather forecast is cold
- Adds a boost to the PI demand (`PREHEAT_BOOST_C = 4°C`) to pre-charge the house
  with thermal mass before heating becomes expensive
- Only makes sense in cold weather — boosting when warm wastes energy with no benefit
- Requires `preheat_boost_enabled = True` in config
- Mode: `preheating`

---

## Summer Mode

When outdoor temperature reaches or exceeds `summer_threshold` (default 18°C), the
system exits all control logic and passes through the real outdoor temperature unchanged.
The heat pump's own summer logic takes over.

Summer mode is the highest-priority check — it short-circuits everything else.

---

## Safe Mode

If any required sensor (indoor temperature, outdoor temperature, or price data) is
unavailable or reports an invalid value, the system enters safe mode and passes through
the real outdoor temperature. No fake offset is applied.

---

## Comfort Floor

The comfort floor determines how far indoor temperature is allowed to drop below the
target before the brake is released, regardless of price:

```
comfort_floor = target − COMFORT_FLOOR_BY_AGGRESSIVENESS[aggressiveness]
```

| Aggressiveness | Allowed drop |
|---|---|
| 0 | 0°C (pure PI, no price logic) |
| 1 | 0.5°C |
| 2 | 1.0°C |
| 3 | 1.5°C (default) |
| 4 | 2.0°C |
| 5 | 3.0°C |

When `indoor < comfort_floor`, the brake is released immediately and `brake_hold` is
set to 0 (no hold time applied).

---

## Home Assistant Integration

- Fully local — no cloud dependencies
- `RestoreEntity` used to survive HA restarts
- Handles `unknown` and `unavailable` sensor states gracefully
- Polling interval: ~60 seconds
- Ohmigo integration: pushes fake temperature to Ohmigo WiFi controller on a
  configurable interval with hysteresis to avoid unnecessary writes

---

## What is Out of Scope

- Machine learning control loops
- Self-modifying parameters
- Black-box optimization engines
- Any behavior that cannot be explained from its inputs alone
