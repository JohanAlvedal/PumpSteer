---
layout: default
title: Configuration
nav_order: 3
---

# ⚙️ Configuration Reference
{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

PumpSteer has two layers of configuration:

- **HA interface** — sliders, switches, and options you set in Home Assistant (take effect after reload)
- **`settings.py`** — advanced constants that require editing the source file and a full HA restart

---

## Setup (config flow)

These are set when you first add the integration. You can change them later via
**Settings → Devices & Services → PumpSteer → Configure**.

| Field | Required | Description |
|---|---|---|
| **Indoor temperature sensor** | ✅ | The sensor PumpSteer uses for current indoor temperature. Must be a `sensor` with `device_class: temperature`. |
| **Outdoor temperature sensor** | ✅ | The real outdoor temperature. PumpSteer manipulates this signal before sending it to the heat pump. |
| **Electricity price sensor** | ✅ | Today's hourly or 15-minute price (e.g. Nordpool). Must have a `today` or `raw_today` attribute containing a list of prices. |
| **Tomorrow price sensor** | ✅ | Tomorrow's prices. Used for lookahead braking and preheat. Can be the same entity if it includes `raw_tomorrow`. |
| **Weather entity** | Optional | A `weather` entity used for forecast-based preheat and precool. Leave empty to disable forecast features. |

---

## Options (configure page)

These can be changed at any time without restarting HA. They take effect on the next
polling cycle after saving.

Go to **Settings → Devices & Services → PumpSteer → Configure** to access these options.

| Field | Description | Default |
|---|---|---|
| **Notification service** | Push service for price alerts, e.g. `notify.mobile_app_my_phone`. Leave empty to use HA persistent notifications. | — |
| **Ohmigo entity** | Number entity to push the fake outdoor temperature to. Leave empty to disable. | — |
| **Ohmigo push interval** | Minimum minutes between Ohmigo pushes. | 5 min |

{: .note }
The notification service is configured directly here in the integration options — no
separate entity or helper needed. Change it at any time without restarting HA.

---

## Number sliders

These appear as entities in the PumpSteer device and can be placed in your dashboard.

---

### 🌡️ Target Temperature

**Entity:** `number.pumpsteer_target_temperature`
**Range:** 16–27 °C · **Step:** 0.5 °C · **Default:** 21 °C

The indoor temperature PumpSteer aims to maintain. The PI controller adjusts the fake
outdoor temperature to drive the heat pump toward this target.

| Setting | Effect |
|---|---|
| Higher | PumpSteer works harder to keep the house warmer |
| Lower | PumpSteer tolerates a cooler indoor temperature |

---

### ☀️ Summer Mode Threshold

**Entity:** `number.pumpsteer_summer_mode_threshold`
**Range:** 10–30 °C · **Step:** 0.5 °C · **Default:** 17 °C

When outdoor temperature reaches this value, PumpSteer enters **summer mode** and
stops controlling the heat pump entirely — passing through the real outdoor temperature
unchanged.

| Setting | Effect |
|---|---|
| Higher | Summer mode activates later (more heating in spring/autumn) |
| Lower | Summer mode activates earlier |

---

### ⚡ Saving Level

**Entity:** `number.pumpsteer_saving_level`
**Range:** 0–5 · **Step:** 1 · **Default:** 3

Controls how aggressively PumpSteer trades comfort for savings during expensive price
periods.

| Level | Behavior | Comfort floor drop allowed |
|---|---|---|
| 0 | Price logic disabled — pure PI control only | 0 °C |
| 1 | Very gentle, barely noticeable | 0.5 °C |
| 2 | Mild saving | 1.0 °C |
| 3 | Balanced *(recommended)* | 1.5 °C |
| 4 | Aggressive saving | 2.0 °C |
| 5 | Maximum saving — noticeable temperature drop | 3.0 °C |

The **comfort floor** is `target − allowed_drop`. When indoor temperature falls below
this floor, the brake releases immediately regardless of price.

{: .note }
At level 0, all price-based logic is disabled. The PI controller runs in pure feedback
mode. This is useful for initial setup and tuning.

---

### 🏠 Brake Ramp Time

**Entity:** `number.pumpsteer_brake_ramp_time`
**Range:** 0.5–10.0 · **Step:** 0.5 · **Default:** 2.0

Controls how long it takes the brake to fully engage (ramp-in) and release (ramp-out).
Set this to match your home's **thermal inertia** — how quickly indoor temperature
responds to changes in heating.

Ramp duration is calculated as:

```
ramp_in  = clamp(value × 6, 15 min, 60 min)
ramp_out = clamp(ramp_in × 0.5, 15 min, 60 min)
```

| Slider value | Ramp in | Ramp out | Suitable for |
|---|---|---|---|
| 0.5–2.5 | 15 min *(min)* | 15 min | Apartments, lightweight houses |
| 3.0 | 18 min | 15 min | Typical Swedish detached house |
| 5.0 | 30 min | 15 min | Larger / heavier houses |
| 7.0 | 42 min | 21 min | Heavy construction |
| 8.0 | 48 min | 24 min | Very heavy construction |
| 9.0 | 54 min | 27 min | Very high thermal mass |
| 10.0 | 60 min *(max)* | 30 min | Exceptional thermal mass |

{: .important }
This slider also controls **pre-brake lead time**. A higher value means PumpSteer
starts the brake ramp earlier before an expensive slot, so the brake is fully engaged
the moment the slot begins. A thermally heavy house needs more lead time.

---

## Switches

### 🔥 Preheat Boost

**Entity:** `switch.pumpsteer_preheat_boost`
**Default:** On

When enabled, PumpSteer heats extra (by `PREHEAT_BOOST_C = 4 °C` equivalent) before
an upcoming expensive period when a simple cold-forecast heuristic (`_forecast_is_cold()`)
returns true. This pre-charges the house with thermal mass so the heat pump can brake
longer without discomfort.

Only activates when:
1. An expensive price slot is coming within the lookahead window
2. The cold-forecast heuristic returns True
3. Indoor temperature is below target (preheat is suppressed if already at target)

{: .note }
`sensor.pumpsteer_thermal_outlook` is diagnostic only and does not yet control this
switch. Preheat decisions are made by the simple `_forecast_is_cold()` heuristic.

Disable this switch if you prefer to avoid pre-heating behavior, or if your forecast
sensor is unreliable.

---

### 🔔 Notifications

**Entity:** `switch.pumpsteer_notifications`
**Default:** On

Enables or disables push notifications when braking or preheating starts.
Notifications are sent to the service configured in the options flow, or via HA
persistent notifications if no service is configured.

---

### 🏖️ Holiday Mode

**Entity:** `switch.pumpsteer_holiday_mode`
**Default:** Off

Lowers the target temperature to `HOLIDAY_TEMP` (default 16 °C) while keeping all
PI and braking logic active. Can also be scheduled using the holiday start/end datetime
helpers.

When the end time is reached, holiday mode deactivates automatically and a notification
is sent.

---

### 📡 Ohmigo Push

**Entity:** `switch.pumpsteer_ohmigo_enabled`
**Default:** On

Enables or disables automatic pushing of the fake outdoor temperature to the configured
Ohmigo number entity. Toggle this without having to reconfigure the options flow.

Pushes are skipped when:
- The new value is within 0.2 °C of the current Ohmigo value (hysteresis)
- Less than `ohmigo_interval_minutes` have passed since the last push

---

## `settings.py` — Advanced constants

These are module-level constants in `custom_components/pumpsteer/settings.py`.
They are evaluated once at import time and require a **full HA restart** (not just
reload) to take effect after editing.

{: .warning }
Only change these if you understand the control logic. Incorrect values can cause
erratic behavior or loss of comfort.

---

### Fake temperature limits

```python
MIN_FAKE_TEMP: Final[float] = -20.0
MAX_FAKE_TEMP: Final[float] = 25.0
```

Hard bounds on the fake outdoor temperature output. PumpSteer will never send a value
outside this range regardless of PI demand or brake state.

Adjust `MIN_FAKE_TEMP` if your heat pump needs a colder signal to heat at maximum
capacity. Adjust `MAX_FAKE_TEMP` if your system behaves oddly at high fake temperatures.

---

### PI controller

```python
PID_KP: Final[float] = 2.4
PID_KI: Final[float] = 0.035
PID_KD: Final[float] = 0.0
PID_INTEGRAL_CLAMP: Final[float] = 6.0
PID_OUTPUT_CLAMP: Final[float] = 12.0
```

| Constant | Effect |
|---|---|
| `PID_KP` | Proportional gain — how strongly PumpSteer reacts to current error. Higher = faster but may oscillate. |
| `PID_KI` | Integral gain — corrects long-term drift. Higher = faster correction but more windup risk. |
| `PID_KD` | Derivative gain — damps fast changes. Leave at 0.0 unless specifically tuning for overshoot. |
| `PID_INTEGRAL_CLAMP` | Maximum absolute value of the integral term. Prevents windup during extended braking. |
| `PID_OUTPUT_CLAMP` | Maximum °C the PI output can add or subtract from the outdoor temperature. |

See the [Tuning Guide](TUNING) for guidance on adjusting these values.

---

### Price classification

```python
PRICE_PERCENTILE_CHEAP: Final[float] = 30.0
PRICE_PERCENTILE_EXPENSIVE: Final[float] = 80.0
ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.50   # SEK/kWh
```

Prices are classified relative to today's price spread:

- Below P30 → `cheap`
- P30 to P80 → `normal`
- Above P80 → `expensive`

If P80 for the day is below `ABSOLUTE_CHEAP_LIMIT`, all slots are classified as cheap
(no braking on days when electricity is universally cheap).

---

### Brake strength

```python
BRAKE_DELTA_C: Final[float] = 10.0
```

How many degrees above real outdoor temperature the fake temperature is pushed during
full braking. A higher value makes the heat pump reduce output more aggressively.

Typical range: 8–15 °C. At 10 °C, most heat pumps will significantly reduce heating
output. At 15 °C, the effect is very strong.

---

### Brake hold time

```python
BRAKE_HOLD_MINUTES: Final[float] = 30.0
```

After an expensive period ends, the brake is held for this many minutes before ramping
out. This prevents oscillation when 15-minute price slots alternate between cheap and
expensive within a longer expensive block.

---

### Preheat boost strength

```python
PREHEAT_BOOST_C: Final[float] = 4.0
```

How much extra heating demand (in °C equivalent) is added during preheat mode.
This is added on top of the PI output, so the total demand is `PI_demand + PREHEAT_BOOST_C`.

---

### Price lookahead

```python
PRICE_LOOKAHEAD_HOURS: Final[int] = 6
```

How many hours ahead PumpSteer scans for upcoming expensive periods when deciding
whether to pre-brake or preheat.

---

### Ramp timing constants

```python
RAMP_SCALE: Final[float] = 6.0
RAMP_MIN_MINUTES: Final[float] = 15.0
RAMP_MAX_MINUTES: Final[float] = 60.0
RAMP_OUT_FACTOR: Final[float] = 0.5
```

`RAMP_SCALE` multiplies the house inertia slider value to get ramp duration in minutes.
`RAMP_OUT_FACTOR` makes the ramp-out faster than ramp-in (0.5 = 50% of ramp-in duration).

---

### Comfort floor

```python
COMFORT_FLOOR_BY_AGGRESSIVENESS: Final[List[float]] = [
    0.0,   # 0 — pure PI
    0.5,   # 1 — very gentle
    1.0,   # 2 — mild
    1.5,   # 3 — balanced
    2.0,   # 4 — aggressive
    3.0,   # 5 — maximum
]
```

The allowed indoor temperature drop below target at each aggressiveness level.
When `indoor < target − floor`, the brake releases immediately.

---

### Holiday temperature

```python
HOLIDAY_TEMP: Final[float] = 16.0
```

The target temperature used when holiday mode is active.

---

### Preheat on missing forecast

```python
PREHEAT_ON_MISSING_FORECAST: Final[bool] = False
```

Controls what happens when forecast data is unavailable:
- `False` *(default)* — preheat boost does not trigger when forecast is missing
- `True` — missing forecast is treated as cold weather; preheat may trigger

The default `False` is safer: it avoids unnecessary preheating if the weather entity
is misconfigured or temporarily unavailable.
