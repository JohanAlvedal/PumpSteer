---
layout: default
title: Troubleshooting
nav_order: 8
---

# 🛠 Troubleshooting
{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Safe Mode is active

**Symptom:** `sensor.pumpsteer` attribute `mode` reads `safe_mode`. The fake
temperature equals the real outdoor temperature.

**Cause:** One or more required inputs are missing or invalid.

**Diagnosis:** Check the `status` attribute of `sensor.pumpsteer` — it contains the
specific reason, e.g.:

```
safe_mode: Missing sensors: indoor sensor 'sensor.indoor_temp' not configured
safe_mode: No price data from today='sensor.elpris_spot_avgifter', tomorrow='...'
```

**Common fixes:**

| Reason in status | Fix |
|---|---|
| Indoor or outdoor sensor missing | Check that the entity ID in the options flow still exists and is available |
| No price data | See [Price sensor not working](#price-sensor-not-working) below |
| Sensor state is `unknown` or `unavailable` | Wait for HA to fully start; sensors recover automatically |

Safe mode resolves itself as soon as valid data is available. No restart needed.

---

## Price sensor not working

**Symptom:** Safe mode due to missing price data, or `price_category` is always `normal`.

**Diagnosis:** PumpSteer reads price data from these attributes on your electricity
price sensor entity:

- `raw_today` — list of today's prices (required)
- `raw_tomorrow` — list of tomorrow's prices (used for lookahead)

Each item must be a dict with a `value` or `price` key, or a plain number:

```json
{ "value": 0.95 }
{ "price": 1.23 }
0.95
```

**Check in Developer Tools → States:**
1. Find your price entity (e.g. `sensor.elpris_spot_avgifter`)
2. Expand attributes
3. Verify `raw_today` exists and contains a list with numeric values

If `raw_today` is missing, your price sensor integration may use a different attribute
name or format. Check the documentation for your Nordpool or Tibber integration.

{: .note }
PumpSteer supports both hourly (24 slots/day) and 15-minute (96 slots/day) price
intervals. The interval is detected automatically from the price data.

---

## Braking never occurs

**Symptom:** Price is expensive but `mode` stays `normal` and the fake temperature
does not rise.

**Possible causes:**

1. **Comfort floor is preventing braking**
   The indoor temperature is below the comfort floor (`target − allowed_drop`).
   Check `comfort_floor_c` in `sensor.pumpsteer` attributes.
   Lower aggressiveness or raise target temperature.

2. **Price is not classified as expensive**
   P80 threshold may be higher than today's peak price.
   Check `p80` attribute on `sensor.pumpsteer`. If all prices are below P80, no
   slot is classified as expensive.
   Also check that `ABSOLUTE_CHEAP_LIMIT` (default 0.50 SEK/kWh) is not making
   all slots cheap — this triggers when P80 itself is below the limit.

3. **Aggressiveness is 0**
   All price logic is disabled at level 0. Raise saving level to at least 1.

4. **Brake ramp has not completed yet**
   Check `brake_factor` in sensor attributes. If it is between 0 and 1, the ramp
   is still building up. This is normal — the ramp takes `ramp_in` minutes.

---

## Braking never stops

**Symptom:** Mode is stuck in `braking` even after the price drops.

**Possible causes:**

1. **Brake hold is active**
   After an expensive slot, the brake holds for `BRAKE_HOLD_MINUTES` (default 30 min)
   before ramping out. This is intentional — it prevents oscillation during short
   cheap dips within a longer expensive block.

2. **Next slot is also expensive**
   Check the `price_category` of upcoming slots. If the next slot is also expensive,
   the brake remains active.

3. **`bridge_short_dip` is active**
   If an expensive period is coming soon after a short cheap window, PumpSteer bridges
   the dip by holding the brake. Check the `bridge_short_dip` attribute.

---

## Wrong price category

**Symptom:** Current price seems wrong for the hour (e.g. classified as expensive when
prices are low).

**Cause:** Price thresholds are cached **once per calendar day** and do not change
mid-day. This is intentional — it prevents brake release during an ongoing expensive
period due to threshold drift.

If thresholds seem clearly wrong:
- Check `p30` and `p80` attributes on `sensor.pumpsteer`
- Compare with today's actual price spread
- Thresholds refresh at midnight when new price data arrives

If tomorrow's prices have not arrived yet (before ~13:00 CET), thresholds are computed
from today's data only. This is correct behavior.

---

## Preheat boost never triggers

**Symptom:** Switch is on, upcoming expensive slots exist, but mode never becomes `preheating`.

**Diagnosis steps:**

1. Check that indoor temperature is **below** target.
   Preheat is suppressed when `indoor_temp >= target_temperature`.

2. Check that the cold-forecast heuristic is satisfied.
   The control loop uses `_forecast_is_cold()` — a simple check based on forecast
   temperature. Check your weather entity is configured and reporting valid forecasts.

3. Check that `raw_tomorrow` is populated on your price entity.
   Lookahead requires tomorrow's prices to be available.

{: .note }
`sensor.pumpsteer_thermal_outlook` attributes like `preheat_worthwhile` are
**diagnostic only** — they do not directly control preheat in the current version.
Use them as context clues, not as a definitive trigger indicator.

---

## Fake temperature seems too extreme

**Symptom:** `sensor.pumpsteer` state is at or near `MIN_FAKE_TEMP` or `MAX_FAKE_TEMP`.

**During normal mode:** A very low fake temperature means the PI is demanding maximum
heating — large error between target and indoor temperature. Check that your target
temperature is not set unrealistically high. Give the integral time to stabilize
(12–24 hours of operation).

**During braking:** The fake temperature rises to `outdoor + BRAKE_DELTA_C`. At very
cold outdoor temperatures (e.g. −15 °C), this may produce a fake temp around −5 °C,
which is correct behavior. The heat pump will still provide some heat at −5 °C.

---

## HA restart causes a large brake ramp jump

**Symptom:** After a restart, `brake_factor` jumps to a high value immediately.

**Cause:** This should not happen with current code. The brake ramp state is persisted
via `RestoreEntity` and the ramp dt is capped at 60 seconds per step.

If you observe this: check that `extra_restore_state_data` is not returning `None` in
logs. This can happen if the entity failed to save state before the restart.

---

## Ohmigo push not working

**Symptom:** `sensor.pumpsteer` updates correctly but Ohmigo value does not change.

**Check these:**

1. `switch.pumpsteer_ohmigo_enabled` is `on`
2. The Ohmigo entity ID in the options flow matches the actual entity
3. The new value differs from the current Ohmigo value by more than 0.2 °C (hysteresis)
4. At least `ohmigo_interval_minutes` have passed since the last push

Check HA logs for `Ohmigo push →` messages to confirm pushes are occurring.

---

## Useful Developer Tools queries

In **Developer Tools → Template**, you can inspect PumpSteer state directly:

```yaml
# Current mode and fake temperature
{{ states('sensor.pumpsteer') }}
{{ state_attr('sensor.pumpsteer', 'mode') }}
{{ state_attr('sensor.pumpsteer', 'price_category') }}
{{ state_attr('sensor.pumpsteer', 'brake_factor') }}
{{ state_attr('sensor.pumpsteer', 'p30') }}
{{ state_attr('sensor.pumpsteer', 'p80') }}

# Thermal outlook
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'preheat_worthwhile') }}
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'preheat_strength') }}
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'warming_trend') }}
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'night_min_temp') }}
```

---

## Enabling debug logging

Add this to your `configuration.yaml` to get detailed PumpSteer logs:

```yaml
logger:
  default: warning
  logs:
    custom_components.pumpsteer: debug
```

Reload the Logger integration (or restart HA), then check **Settings → System → Logs**.
PumpSteer will log PI calculations, mode transitions, price threshold computations,
brake ramp updates, and Ohmigo push events.

---

## Safety reminder

{: .warning }
Heating is a critical system. PumpSteer's safe mode passes through the real outdoor
temperature unchanged, so the heat pump continues to operate on its own heating curve
even if PumpSteer loses sensor data. Monitor your system for the first few days after
installation and after any configuration changes.
