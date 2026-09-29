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

**Diagnosis:** PumpSteer accepts these list attributes on the configured electricity
price entities:

- `today` or `raw_today` — today's prices
- `tomorrow` or `raw_tomorrow` — tomorrow's prices used for lookahead

Each item must be a dict with a `value` or `price` key, or a plain number:

```json
{ "value": 0.95 }
{ "price": 1.23 }
0.95
```

**Check in Developer Tools → States:**
1. Find your price entity (e.g. `sensor.elpris_spot_avgifter`)
2. Expand attributes
3. Verify `today` or `raw_today` contains a list with usable numeric prices

If neither supported attribute exists, your price integration may use a different
format. Check the integration's documentation. PumpSteer accepts plain numbers and
objects with a numeric `value` or `price` field.

{: .note }
PumpSteer supports both hourly (24 slots/day) and 15-minute (96 slots/day) price
intervals. The interval is detected automatically from the price data.

---

## Braking never occurs

**Symptom:** Price is expensive but `mode` stays `normal` and the fake temperature
does not rise.

**Possible causes:**

1. **Comfort floor is preventing braking or pre-braking**
   The indoor temperature is below the comfort floor (`target − allowed_drop`).
   This blocks a new pre-brake and releases an existing brake/pre-brake ramp.
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

## Brake factor remains active after the price drops

**Symptom:** Price is no longer expensive, but the brake factor remains above zero or
the mode changes to `brake_hold`.

**Possible causes:**

1. **Short-dip bridge is active**
   PumpSteer holds the current brake factor only when the next expensive period starts
   within `BRAKE_HOLD_MINUTES` (default 30 min). If the next expensive period is farther
   away, the brake should ramp out immediately.

2. **Next slot is also expensive**
   Check the `price_category` of upcoming slots. If the next slot is also expensive,
   the brake remains active.

3. **`bridge_short_dip` is active**
   If an expensive period is coming within the configured bridge window, PumpSteer
   preserves the current brake factor across the short dip. The factor should stay flat,
   not continue ramping upward. Check `bridge_short_dip`, `minutes_until_expensive`, and
   `bridge_limit_minutes` in the sensor attributes.

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

P30/P80 thresholds are intentionally computed from **today's price list only**.
Tomorrow prices are used for lookahead decisions, not for changing today's cached
classification thresholds.

---

## Preheat boost never triggers

**Symptom:** Switch is on, upcoming expensive slots exist, but mode never becomes `preheating`.

**Diagnosis steps:**

1. Check the thermal headroom.
   Preheat can continue slightly above target, but the boost tapers to zero at
   `target + preheat_headroom_c`. Check `preheat_headroom_c`,
   `preheat_ceiling_c`, and `preheat_headroom_factor` on `sensor.pumpsteer`.
   At a headroom factor of 0.0, extra preheat is intentionally blocked.

2. Check `sensor.pumpsteer_thermal_outlook`.
   When ThermalOutlook is available, `preheat_worthwhile` must be true and
   `preheat_strength` scales how much boost is used. If ThermalOutlook cannot be
   built, PumpSteer falls back to the simpler `_forecast_is_cold()` check.

3. Check that valid future price data exists.
   Preheat only runs when an expensive period is inside the configured lookahead.
   Tomorrow data is needed when that period crosses into the next day.

4. Check that `switch.pumpsteer_preheat_boost` is on.

The maximum preheat headroom is 0.3 / 0.5 / 0.7 / 1.0 / 1.5 °C for saving levels
1 through 5 respectively.

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
3. At least `ohmigo_interval_minutes` have passed since the last Ohmigo command
4. Changes smaller than 0.2 °C are treated as an unchanged setpoint, but the current setpoint is still resent when the interval is due to keep the Ohmigo watchdog alive

Check HA debug logs for `Ohmigo push` or `Ohmigo keepalive resend` messages to confirm commands are occurring.

---

## Ohmigo Relay Guard does not recover the relay

**Symptom:** A configured Active/Bypass relay is off, but Relay Guard does not turn it on.

Check these gates:

1. `switch.pumpsteer_ohmigo_relay_guard` is `on`
2. `switch.pumpsteer_ohmigo_enabled` (Ohmigo Push) is explicitly `on`
3. The configured relay explicitly reports `off`

If the relay is `unknown`, `unavailable` or missing, Relay Guard intentionally sends
no command. This fail-closed behavior avoids guessing the state of the physical signal
path.

When recovery is eligible, Relay Guard waits briefly for state stabilization, then
tries `switch.turn_on` at most three times. A service call is not considered success
until the relay itself reports `on`.

Inspect the Relay Guard switch attributes for:

- `status`
- `relay_state`
- `ohmigo_push_state`
- `recovery_attempts`
- `last_recovery`
- `last_failure`

`safe_mode` alone does not inhibit Relay Guard. Ohmigo may still be forwarding the
real outdoor temperature, so the Active path can still be required.

---

## Useful Developer Tools queries

In **Developer Tools → Template**, you can inspect PumpSteer state directly:

```yaml
# Current mode and fake temperature
{{ states('sensor.pumpsteer') }}
{{ state_attr('sensor.pumpsteer', 'mode') }}
{{ state_attr('sensor.pumpsteer', 'price_category') }}
{{ state_attr('sensor.pumpsteer', 'current_price') }}
{{ state_attr('sensor.pumpsteer', 'current_price_unit') }}
{{ state_attr('sensor.pumpsteer', 'brake_factor') }}
{{ state_attr('sensor.pumpsteer', 'p30') }}
{{ state_attr('sensor.pumpsteer', 'p80') }}
{{ state_attr('sensor.pumpsteer', 'thermal_k') }}
{{ state_attr('sensor.pumpsteer', 'thermal_k_valid') }}
{{ state_attr('sensor.pumpsteer', 'thermal_k_samples') }}

# Thermal outlook
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'preheat_worthwhile') }}
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'preheat_strength') }}
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'warming_trend') }}
{{ state_attr('sensor.pumpsteer_thermal_outlook', 'night_min_temp') }}
```

---

## PumpSteer diagnostic log files

PumpSteer writes a structured diagnostic log to:

```
/config/pump.log
```

The log is **diagnostic only**. PumpSteer does not read log entries back into the
controller and does not use `pump.log` for PI control, price braking, preheat decisions,
or ThermalModel calculations. Deleting old diagnostic logs therefore does not change
control behavior.

Current versions do not use a `/config/pumplog/` directory. If such a directory exists,
it is legacy data from an older setup and can be removed.

Log rotation is simple: when PumpSteer initializes, a `pump.log` larger than 1 MB is
renamed to `pump.log.1`, replacing any older `pump.log.1` file.

{: .note }
Old rotated logs and legacy `pumplog` files can be deleted at any time. Avoid deleting
the active `/config/pump.log` while Home Assistant is running, because PumpSteer may
still have the file open. If the active file is removed, perform a full Home Assistant
restart to ensure a new `pump.log` is created and logging resumes normally.

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
Heating is a critical system. In safe mode PumpSteer passes through the real outdoor
temperature when that sensor is still available, so the heat pump can continue on its
own heating curve. If the outdoor sensor itself is unavailable, PumpSteer's output is
also unavailable. Monitor the system after installation and configuration changes.
