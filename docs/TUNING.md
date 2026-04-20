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

This means roughly 70% of hours are normal and 20% are expensive.

If you want to brake less frequently (fewer hours classified as expensive), raise
`PRICE_PERCENTILE_EXPENSIVE` toward 90. If you want to brake more often, lower it toward 70.

If electricity is universally cheap (e.g. below `ABSOLUTE_CHEAP_LIMIT = 0.50 SEK/kWh`),
all slots are classified as cheap regardless of percentile — no braking occurs.

---

## Forecast and Preheat

Preheat boost (`switch.pumpsteer_preheat_boost`) only triggers when:

1. An expensive slot is coming within the lookahead window
2. The weather forecast shows cold conditions (`_forecast_is_cold()` returns True)

If preheat never triggers but you expect it to:

- Check that your weather entity is correctly configured in the options flow
- Check `sensor.pumpsteer_thermal_outlook` attributes: `preheat_worthwhile` should be `true`
- Ensure the price sensor has `raw_tomorrow` populated (required for lookahead)

If preheat triggers too often or during warm weather:

- This indicates the weather entity is reporting cold temps even when it should not
- Check the `sensor.pumpsteer_thermal_outlook` → `warming_trend` and `day_max_temp` attributes
- Consider lowering `PRECOOL_MARGIN` in `settings.py` if you see unwanted precool behavior

---

## Recorder Requirement

PumpSteer reads price history from the HA Recorder to compute daily thresholds.
The integration requires at least a few hours of recorded price data on the first day.
This is normally satisfied automatically as long as the Recorder integration is active
(it is enabled by default in HA).

If you see safe mode triggered with a reason mentioning price data, check that:
- Your price sensor is reporting valid states
- The `raw_today` attribute contains a list of numeric prices
- The Recorder is active and not excluded from recording the price sensor
