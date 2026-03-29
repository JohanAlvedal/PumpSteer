# PumpSteer – Configuration Reference

This document covers all settings available in PumpSteer, split into two sections:

- **[HA Interface](#ha-interface)** — sliders, switches and entity pickers you configure in Home Assistant
- **[settings.py](#settingspy)** — advanced constants that require a code change and integration reload

-----

## HA Interface

### Setup (config flow)

These are set once when you first add the integration. You can change them later via **Configure** in the integration page.

|Field                                |Description                                                                                                                         |
|-------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
|**Indoor temperature sensor**        |The sensor PumpSteer reads for current indoor temperature. Must be a `sensor` with `device_class: temperature`.                     |
|**Outdoor temperature sensor**       |The real outdoor temperature sensor. PumpSteer manipulates this signal before sending it to the heat pump.                          |
|**Electricity price sensor**         |Today’s hourly/quarter-hourly spot price sensor (e.g. Nordpool). Must have a `today` or `raw_today` attribute with a list of prices.|
|**Tomorrow electricity price sensor**|Tomorrow’s price sensor. Used for lookahead braking and preheating.                                                                 |
|**Weather entity** *(optional)*      |A `weather` entity used for forecast-based preheating and precooling. Leave empty to disable forecast features.                     |

-----

### Options (configure page)

These can be changed at any time without restarting HA.

|Field                                |Description                                                                                                                       |Default|
|-------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|-------|
|**Notification service** *(optional)*|Notify service to use for price alerts, e.g. `notify.mobile_app_my_phone`. Leave empty to use HA persistent notifications instead.|—      |

-----

### Sliders (`number` entities)

Found in the PumpSteer device page or your dashboard.

#### 🌡️ Target Temperature

`number.pumpsteer_target_temperature` · Range: 16–27 °C · Step: 0.5

The indoor temperature PumpSteer aims to maintain. The PI controller adjusts the fake outdoor temperature to push the heat pump toward this target.

**Example:**
- Higher value = PumpSteer tries to keep the house warmer
- Lower value = PumpSteer allows a cooler indoor temperature

-----

#### ☀️ Summer Mode Threshold

`number.pumpsteer_summer_mode_threshold` · Range: 10–30 °C · Step: 0.5

When outdoor temperature reaches this value, PumpSteer enters **summer mode** and stops controlling the heat pump (passes through the real outdoor temperature unchanged).

**Example:**
- Higher value = summer mode activates later
- Lower value = summer mode activates earlier

-----

#### ⚡ Saving Level

`number.pumpsteer_saving_level` · Range: 0–5 · Step: 1

Controls how aggressively PumpSteer trades comfort for savings during expensive price periods.

|Level|Behaviour                                              |
|-----|-------------------------------------------------------|
|0    |Price control disabled — pure PI comfort control       |
|1    |Very gentle, barely noticeable                         |
|2    |Mild saving                                            |
|3    |Balanced *(recommended)*                               |
|4    |Aggressive saving                                      |
|5    |Maximum saving — indoor temperature may drop noticeably|

At level 0 the brake and all price logic is bypassed entirely. At higher levels, the **comfort floor** (see `settings.py`) determines how far the indoor temperature is allowed to drop before the brake is released.

**Example:**
- Higher value = more savings, but indoor comfort may vary more
- Lower value = less savings, but more stable indoor comfort

-----

#### 🏠 Brake Ramp Time

`number.pumpsteer_brake_ramp_time` · Range: 0.5–10.0 · Step: 0.5

Controls how long the brake ramp takes to fully engage. Higher value = slower, smoother transition into braking.

The ramp time is calculated as:

```python
ramp_in  = max(RAMP_MIN, min(RAMP_MAX, value × RAMP_SCALE))
ramp_out = max(RAMP_MIN, ramp_in × 0.5)
````

With default `RAMP_SCALE = 10`:

| Slider value | Ramp in            | Ramp out |
| ------------ | ------------------ | -------- |
| 0.5–2.0      | 20 min *(minimum)* | 20 min   |
| 3.0          | 30 min             | 20 min   |
| 4.0          | 40 min             | 20 min   |
| 5.0          | 50 min             | 25 min   |
| 6.0+         | 60 min *(maximum)* | 30 min   |

> **Note:** Values below 2.0 all give the minimum ramp time because `1 × 2.0 × 10 = 20 = RAMP_MIN`. To see a difference you need to go above 2.0.

**Example:**

* Higher value = braking ramps in more slowly and smoothly
* Lower value = braking reacts faster and more sharply

---

### Switches

#### 🔔 Notifications

`switch.pumpsteer_notifications`

Enables or disables push notifications when braking starts or preheating starts. Uses the notification service configured in options, or HA persistent notifications if none is set.

#### 🏖️ Holiday Mode

`switch.pumpsteer_holiday_mode`

Lowers the target temperature to `HOLIDAY_TEMP` (default 16 °C). The PI controller and braking logic continue running normally at the lower target. Use the holiday start/end datetime entities to schedule this automatically.

---

## settings.py

These constants require editing `custom_components/pumpsteer/settings.py` and reloading the integration. They are intended for advanced tuning — the defaults are reasonable for most setups.

---

### Fake temperature limits

```python
MIN_FAKE_TEMP: Final[float] = -20.0
MAX_FAKE_TEMP: Final[float] = 25.0
```

Hard bounds on the fake outdoor temperature sent to the heat pump. If the PI controller or brake calculation would exceed these, the value is clamped. Raise `MAX_FAKE_TEMP` slightly if your heat pump needs a warmer signal in summer/precool mode.

**Example:**

* Higher `MAX_FAKE_TEMP` = allows a warmer fake outdoor signal before clamping
* Lower `MAX_FAKE_TEMP` = limits how far PumpSteer can push the signal upward
* Lower `MIN_FAKE_TEMP` = allows a colder fake outdoor signal before clamping
* Higher `MIN_FAKE_TEMP` = gives a narrower control range downward

---

### Summer / precool

```python
PRECOOL_LOOKAHEAD: Final[int] = 24    # hours ahead to scan for warm forecast
PRECOOL_MARGIN: Final[float] = 3.0   # °C above summer threshold to trigger precool
```

Precooling engages when any forecast temperature within `PRECOOL_LOOKAHEAD` hours exceeds `summer_threshold + PRECOOL_MARGIN`. It raises the fake outdoor temperature to discourage the heat pump from adding heat before summer.

**Example:**

* Higher `PRECOOL_LOOKAHEAD` = PumpSteer looks further ahead for warm weather
* Lower `PRECOOL_LOOKAHEAD` = PumpSteer reacts more short-term
* Higher `PRECOOL_MARGIN` = precool activates only for clearly warmer forecasts
* Lower `PRECOOL_MARGIN` = precool activates more easily

---

### PI controller

```python
PID_KP: Final[float] = 2.4       # proportional gain
PID_KI: Final[float] = 0.035     # integral gain
PID_KD: Final[float] = 0.0       # derivative gain (leave at 0 unless you know what you're doing)
PID_INTEGRAL_CLAMP: Final[float] = 6.0   # max built-up integral correction (°C)
PID_OUTPUT_CLAMP: Final[float] = 12.0    # max total PI output (°C)
```

The PI controller keeps indoor temperature at target by adjusting the fake outdoor temperature. Higher `KP` = faster reaction to current error. Higher `KI` = stronger correction of long-term drift. The integral is frozen (not reset) during braking to avoid a large heat burst when braking ends.

**Example:**

* Higher `PID_KP` = faster reaction to temperature error, but more risk of oscillation
* Lower `PID_KP` = slower and softer reaction
* Higher `PID_KI` = stronger correction of long-term drift
* Lower `PID_KI` = gentler long-term correction, but slower recovery
* Higher `PID_KD` = more damping of fast changes, if used
* Lower `PID_KD` = less damping effect
* Higher `PID_INTEGRAL_CLAMP` = allows more built-up integral correction
* Lower `PID_INTEGRAL_CLAMP` = limits how much integral correction can accumulate
* Higher `PID_OUTPUT_CLAMP` = allows stronger total PI correction
* Lower `PID_OUTPUT_CLAMP` = limits the maximum PI effect

---

### Price classification

```python
PRICE_PERCENTILE_CHEAP: Final[float] = 30.0      # below P30 = cheap
PRICE_PERCENTILE_EXPENSIVE: Final[float] = 80.0  # above P80 = expensive
DEFAULT_TRAILING_HOURS: Final[int] = 72           # history window for percentiles
MIN_SAMPLES_FOR_CLASSIFICATION: Final[int] = 5
ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.60        # always cheap below this (SEK/kWh)
```

Prices are classified relative to the last 72 hours of history. The percentile thresholds determine the cheap/normal/expensive bands. `ABSOLUTE_CHEAP_LIMIT` overrides the percentile — a price below this is always classified as cheap regardless of history (useful when all recent prices are low).

**Example:**

* Higher `PRICE_PERCENTILE_CHEAP` = fewer hours are treated as cheap
* Lower `PRICE_PERCENTILE_CHEAP` = more hours are treated as cheap
* Lower `PRICE_PERCENTILE_EXPENSIVE` = more hours are treated as expensive
* Higher `PRICE_PERCENTILE_EXPENSIVE` = fewer hours are treated as expensive
* Higher `DEFAULT_TRAILING_HOURS` = slower, more stable classification based on longer history
* Lower `DEFAULT_TRAILING_HOURS` = more reactive classification
* Higher `MIN_SAMPLES_FOR_CLASSIFICATION` = requires more price data before classification starts
* Lower `MIN_SAMPLES_FOR_CLASSIFICATION` = classification starts sooner with less data
* Higher `ABSOLUTE_CHEAP_LIMIT` = more prices are always classified as cheap
* Lower `ABSOLUTE_CHEAP_LIMIT` = only very low prices are always classified as cheap

---

### Comfort floor

```python
COMFORT_FLOOR_BY_AGGRESSIVENESS: Final[List[float]] = [
    0.0,  # level 0 — no price control
    0.5,  # level 1
    1.0,  # level 2
    1.5,  # level 3
    2.0,  # level 4
    3.0,  # level 5
]
```

How many °C below target the indoor temperature is allowed to drop before the brake is released, per saving level. At level 3 with target 21 °C, the brake releases if indoor drops below 19.5 °C. Must have exactly 6 entries.

**Example:**

* Higher values = more savings, because PumpSteer allows a larger indoor drop before releasing the brake
* Lower values = tighter comfort protection, because the brake is released sooner

---

### Brake strength

```python
BRAKE_DELTA_C: Final[float] = 10.0
```

During braking, the fake outdoor temperature is set to `outdoor + BRAKE_DELTA_C`. This makes the heat pump think it is warmer outside than it is, reducing heating output. Higher value = stronger braking. Practical range: 8–18 °C. Above ~18 °C the heat pump may shut down entirely.

**Example:**

* Higher value = stronger braking and less heating output
* Lower value = softer braking and more continued heating

---

### Ramp timing

```python
RAMP_SCALE: Final[float] = 10.0         # multiplier in ramp formula
RAMP_MIN_MINUTES: Final[float] = 20.0   # floor — never shorter than this
RAMP_MAX_MINUTES: Final[float] = 60.0   # ceiling — never longer than this
```

Controls how long the brake takes to ramp in and out. The actual ramp time is computed from the **Brake Ramp Time** slider:

```python
ramp_in = clamp(slider × RAMP_SCALE, RAMP_MIN, RAMP_MAX)
```

Raise `RAMP_SCALE` to give the slider more range without needing high slider values. Raise `RAMP_MAX_MINUTES` if you have a very heavy house and want even smoother transitions.

**Example:**

* Higher `RAMP_SCALE` = the slider has a bigger effect on ramp time
* Lower `RAMP_SCALE` = the slider changes ramp time less
* Higher `RAMP_MIN_MINUTES` = even the fastest braking becomes smoother
* Lower `RAMP_MIN_MINUTES` = allows quicker braking response
* Higher `RAMP_MAX_MINUTES` = allows very slow and smooth ramping
* Lower `RAMP_MAX_MINUTES` = caps the ramp to a shorter maximum time

---

### Preheating

```python
PREHEAT_BOOST_C: Final[float] = 4.0
```

Extra heating demand added on top of the PI output during the preheat window (before an expensive period, when it is cold). Raises the fake outdoor temperature slightly lower (more heating) to build up thermal mass. Only active when `preheat_boost_enabled` is True (default).

**Example:**

* Higher value = stronger preheating before expensive periods
* Lower value = gentler preheating

---

### Peak filter

```python
PEAK_FILTER_MIN_DURATION_MINUTES: Final[int] = 30
```

Expensive price spikes shorter than this are ignored. Prevents the brake from engaging for a single 15-minute expensive slot surrounded by cheap slots.

**Example:**

* Higher value = more short expensive spikes are ignored
* Lower value = PumpSteer reacts to shorter spikes

---

### Price lookahead

```python
PRICE_LOOKAHEAD_HOURS: Final[int] = 6
```

How many hours ahead PumpSteer scans for upcoming expensive periods when deciding whether to start preheating or pre-braking.

**Example:**

* Higher value = more forward-looking planning
* Lower value = more reactive, short-term behavior

---

### Brake hold time

```python
BRAKE_HOLD_MINUTES: Final[float] = 30.0
```

After the price drops from expensive to normal, the brake is held for this many minutes before releasing. Prevents rapid on/off cycling when there is a short cheap dip in the middle of an expensive block.

**Example:**

* Higher value = brake stays active longer after expensive periods
* Lower value = brake releases sooner

---

### Preheating on missing forecast

```python
PREHEAT_ON_MISSING_FORECAST: Final[bool] = False
```

What to do when the weather entity has no forecast data. `False` (default) = no preheating triggered. `True` = treat missing forecast as cold weather and allow preheating. Recommended to leave at `False` unless your weather entity is frequently unavailable and you are in a cold climate.

**Example:**

* `True` = more aggressive fallback behavior when forecast data is missing
* `False` = safer and more conservative behavior when forecast data is missing

---

### Holiday temperature

```python
HOLIDAY_TEMP: Final[float] = 16.0
```

The target temperature used when Holiday Mode is active.

**Example:**

* Higher value = warmer indoor temperature during holiday mode
* Lower value = more energy saving during holiday mode
