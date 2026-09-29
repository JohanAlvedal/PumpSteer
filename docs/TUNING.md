---
layout: default
title: Tuning Guide
nav_order: 6
---

# 🔧 Tuning Guide
{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

PumpSteer works out of the box with default settings for most Swedish detached houses.
This guide helps you get better results by matching the settings to your specific home.

---

## Start here: Saving Level

The **Saving Level** slider (`number.pumpsteer_saving_level`) is the single most
important setting. It controls both how hard PumpSteer brakes during expensive
electricity slots and how much indoor temperature is allowed to drop.

**Start at level 3** (the default) and observe for a week. Then:

- If the house feels too cold during expensive periods → lower to 2
- If you want more savings and the temperature drop is acceptable → raise to 4
- If you want pure comfort with no price logic → set to 0

{: .note }
At level 0, all price braking and preheat logic is completely disabled. PumpSteer
becomes a pure PI temperature controller. This is a good starting point for initial
setup and fault isolation.

---

## Brake Ramp Time (House Inertia)

The **Brake Ramp Time** slider (`number.pumpsteer_brake_ramp_time`) should match how
quickly your home responds to changes in heating.

### How to find your home's inertia

A simple test: set the heat pump to minimum output and observe how long it takes before
indoor temperature starts falling noticeably. A slow drop = high inertia.

| Home type | Typical value |
|---|---|
| Apartment or lightweight wooden house | 0.5–1.5 |
| Standard Swedish detached house | 2.0–3.0 *(default: 2.0)* |
| Larger house, mixed construction | 3.0–5.0 |
| Heavy stone or concrete construction | 5.0–10.0 |

### What this slider actually controls

Ramp time determines two things:

1. **How quickly the brake engages and releases** — higher value = smoother transitions
2. **How early pre-brake starts** — a higher inertia house starts the ramp earlier
   so the brake is fully engaged when the expensive slot begins

A ramp that is too short can cause abrupt fake-temperature steps that wear the
compressor. A ramp that is too long delays the brake and reduces savings.

---

## PI Controller (Advanced)

The PI controller defaults (`KP = 2.4`, `KI = 0.035`) work well for most homes.
Only adjust these if you observe specific problems:

### Symptom: Indoor temperature oscillates (overshoots and corrects repeatedly)

**Cause:** KP is too high relative to your home's thermal mass.

**Fix:** Lower `PID_KP` in `settings.py`, e.g. from 2.4 to 1.8. Requires full restart.

### Symptom: Indoor temperature takes a very long time to reach target after a brake

**Cause:** KI is too low, or the integral was reset unexpectedly.

**Fix:** Slightly raise `PID_KI`, e.g. from 0.035 to 0.050. The integral accumulates
slowly by design to avoid windup. Give it a full heating cycle before judging.

### Symptom: Temperature consistently sits 0.5–1 °C below target even with no braking

**Cause:** Normal during initial operation. The integral builds up over several hours.

**Fix:** Wait at least 12 hours. The integral term accumulates slowly and will correct
steady-state errors over time. If the problem persists after 24 hours, raise KI slightly.

### Symptom: The fake temperature is always at the maximum or minimum

**Cause:** `PID_OUTPUT_CLAMP` may be too high, or there is a large sustained error.

**Fix:** Check that your target temperature is realistic. If indoor is far below target
for non-PI reasons (e.g. a cold snap after a long brake), the integral will ramp up
naturally — this is correct behavior, not windup.

{: .important }
The PI integral is **frozen** (not reset) during braking. This is intentional: when
the brake releases, the PI immediately knows how much heating was needed before, so
it resumes at the right output level without lag. Do not interpret a non-zero integral
during braking as a problem.

---

## Brake Strength

`BRAKE_DELTA_C` (default 10 °C) controls how far the fake temperature is raised above
real outdoor temperature during full braking.

At `BRAKE_DELTA_C = 10`:
- If it is −5 °C outside, the heat pump sees +5 °C
- Most heat pumps will significantly reduce heating output at this signal

If your heat pump does not respond sufficiently to braking, increase to 12–15 °C.
If braking causes the indoor temperature to drop faster than the comfort floor allows,
the brake will release automatically — so raising this value is generally safe.

{: .warning }
Very high values (above 15 °C) combined with high aggressiveness may cause the
comfort floor to trigger frequently, producing rapid brake cycling. Prefer raising the
aggressiveness level before increasing brake delta.

---

## Price Classification Thresholds

By default, prices are classified relative to today's spread:

- Below P30 → `cheap`
- P30 to P80 → `normal`
- Above P80 → `expensive`

Ignoring the absolute-cheap override, this corresponds roughly to 30% cheap, 50% normal and 20% expensive slots.

If you want to brake less frequently (fewer hours classified as expensive), raise
`PRICE_PERCENTILE_EXPENSIVE` toward 90. If you want to brake more often, lower it toward 70.

If electricity is universally cheap (e.g. below `ABSOLUTE_CHEAP_LIMIT = 0.50 SEK/kWh`),
all slots are classified as cheap regardless of percentile — no braking occurs.

---

## Forecast and Preheat

Preheat boost (`switch.pumpsteer_preheat_boost`) is an overlay on the ordinary PI
comfort loop. It can activate when:

1. An expensive period is inside the lookahead window
2. ThermalOutlook says preheating is worthwhile, or the cold-forecast fallback is used
   because ThermalOutlook is unavailable
3. Thermal headroom remains
4. The Preheat Boost switch is on

When ThermalOutlook is available, `preheat_strength` scales the boost. PumpSteer can
preheat slightly above the normal target: saving levels 1–5 allow 0.3 / 0.5 / 0.7 /
1.0 / 1.5 °C of headroom. The boost tapers linearly above target and reaches zero at
the headroom ceiling.

If preheat never triggers but you expect it to:

- Check that the weather entity is correctly configured and returning a forecast
- Check `sensor.pumpsteer_thermal_outlook` → `preheat_worthwhile` and `preheat_strength`
- Verify tomorrow/lookahead prices are available from `tomorrow` or `raw_tomorrow`
- Check `preheat_headroom_factor`; 0.0 means the thermal ceiling has been reached
- Confirm `switch.pumpsteer_preheat_boost` is on

If preheat triggers too often or during warm weather:

- Inspect ThermalOutlook's `warming_trend`, `day_max_temp` and `preheat_strength`
- Verify the configured weather entity represents the home's actual local conditions
- Check the saving level: higher levels intentionally allow more preheat headroom

---

## Price data and Recorder

The active P30/P80 control thresholds are computed from **today's available price
list** and cached for the calendar day. PumpSteer does not require recorded price
history from Home Assistant Recorder for the current daily classification strategy.

The integration still declares Recorder as a dependency, but Recorder history is not
what drives today's P30/P80 thresholds.

If safe mode reports missing price data, check that:

- the configured price entity exists and is available
- today's prices are present in `today` or `raw_today`
- tomorrow prices, when used for lookahead, are present in `tomorrow` or `raw_tomorrow`
- list entries are plain numbers or objects containing a numeric `value` / `price`
