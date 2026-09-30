---
layout: default
title: Design Decisions
nav_order: 10
---

# ⚖️ Design Decisions
{: .no_toc }

This document records *why* key design decisions were made — not what the code does
(that belongs in comments and Architecture), but the reasoning behind choices where
a different approach was considered and rejected.

Use this to avoid relitigating settled questions and to understand the trade-offs
before proposing changes.

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## PI Controller

### Why freeze the integral during braking, not decay or reset

**Decision:** `brake_behavior = "freeze"` — integral is held constant while the brake
is active.

**Alternatives considered:**
- `decay` — integral slowly decreases toward zero during braking
- `reset` — integral is zeroed when braking starts

**Why freeze wins:**
The house loses heat while the brake is active, particularly in autumn/winter/spring.
When the brake releases, the PI needs an accurate picture of how much heating was
required *before* the brake — the frozen integral provides exactly that.

Decaying the integral means the PI underestimates demand when it takes over again,
causing a lag before comfort is restored. This lag is more harmful in cold weather,
which is precisely when the brake is most likely to be used.

Resetting is even worse — the PI starts from zero with no memory of prior thermal demand.

**Conclusion:** Freeze is the correct behavior for the target climate (Swedish winters).

---

## Price Classification

### Why thresholds are cached per calendar day

**Decision:** P30 and P80 thresholds are computed once per calendar day and cached.
They do not update during the day even if new price data arrives.

**Problem this solves:**
Recomputing thresholds hourly caused mid-slot reclassification. P80 could shift just
enough during an ongoing expensive slot to flip it to "normal", releasing the brake
unexpectedly mid-hour. This produced erratic behavior that was hard to diagnose.

**Why per-day caching is stable:**
Price data for tomorrow arrives at ~13:00 CET. At that point the cache refreshes for
the next midnight boundary anyway. Within a single day, the shape of the price curve
is known and stable — there is no good reason to reclassify slots that are already
in progress.

**Side effect:** If price data arrives significantly late (e.g. sensor unavailable at
midnight), the previous day's thresholds remain until data is available. This is
acceptable — stale thresholds are better than mid-slot reclassification.

---

### Why hybrid history/horizon weighting is not yet implemented

**Status: constants exist, not applied.**

`HISTORY_WEIGHT` and `HORIZON_WEIGHT` are defined in `settings.py` (both 0.50) but
are not applied. The current logic uses **today's known prices only** — consistent with
how Ngenic/Tibber classify prices relative to the current day's spread.

**Intended future design:**
```
P80_hybrid = HISTORY_WEIGHT × P80_history + HORIZON_WEIGHT × P80_today_tomorrow
```

Pure history problem: thresholds adapt slowly during prolonged cheap periods.
Pure horizon problem: thresholds become volatile on a single high-price day.
A 50/50 blend would balance stability and daily adaptability.

This is unfinished work — do not treat it as implemented behavior.

---

## Brake Mechanics

### Why dt is capped at 60 seconds in the brake ramp

**Decision:** `dt_s = min(actual_dt, 60)` in `_update_brake_ramp()`.

**Problem this solves:**
After an HA restart or a long gap between polling cycles, `actual_dt` could be many
minutes. Without the cap, a single ramp step would jump the brake factor by a large
amount — effectively skipping the ramp entirely.

The cap ensures the ramp always advances by at most one polling cycle worth of progress
per step, regardless of how much real time has passed.

**Why 60 seconds:** The polling interval is approximately 60 seconds. Capping at 60s
means the worst case is one "missed" cycle — imperceptible in practice.

---

### Why brake hold exists

**Decision:** A non-expensive gap is bridged only when the next expensive period begins within
`BRAKE_HOLD_MINUTES` (default 30 min). Otherwise the brake starts ramping out immediately.

**Problem this solves:**
Price data at 15-minute resolution can produce alternating expensive/cheap/expensive
slots within a longer expensive block. Without hold, the brake would ramp out during
the cheap dip and then immediately ramp in again — causing oscillation and extra wear.

30 minutes covers two 15-minute cheap slots — enough to bridge typical intra-block
dips without allowing a distant expensive period, for example several hours away, to
keep the system unnecessarily braked.

**Factor behavior during a bridge:**
The current brake factor is held constant. A bridge is not treated as a new brake
request, because doing so would continue ramping the brake upward during a cheap/normal
slot instead of merely preserving the existing brake state.

**When hold is bypassed:**
If `indoor < comfort_floor`, hold is set to 0 and the brake releases immediately
regardless of the hold timer. Comfort always takes precedence.

---

## Block Structure

### Why pre-brake (5a) and preheat-boost (5b) are separate blocks

**Decision:** Two distinct blocks with different trigger conditions and different mode
strings (`pre_braking` vs `preheating`).

**Pre-brake (5a):**
- Pure price signal: imminent expensive period within `ramp_in` minutes
- No forecast dependency
- Still subject to the same comfort floor as active braking
- Goal: brake at full factor exactly when the expensive slot starts, without sacrificing the configured comfort floor

**Preheat-boost (5b):**
- Forecast signal: imminent expensive period AND cold weather coming
- Only makes sense when cold — boosting in warm weather wastes energy
- Goal: pre-charge the house with thermal mass

**Why they were previously confused:**
Both used to share the `"preheating"` mode string, making it impossible to distinguish
them in logs, dashboards, or notification triggers. Separating them makes the state
machine explicit and testable.

**Why 5a must not be forecast-gated:**
Forecast data can be unavailable (misconfigured sensor, API outage). Gating 5a on
forecast would cause the brake to miss its window whenever forecast is unavailable.

**Why the comfort floor still applies to 5a:**
Pre-brake is only an early phase of the same heat-reduction strategy used during an
expensive slot. Starting that reduction when the house is already below its configured
comfort floor would make the price signal override comfort. Therefore the comfort floor
blocks a new pre-brake and causes an existing pre-brake ramp to release.

---

### Why preheat headroom follows saving level and tapers gradually

**Decision:** Preheat may charge the house slightly above the normal target, but the
maximum allowed headroom is tied to saving level: 0.0, 0.3, 0.5, 0.7, 1.0 and 1.5 °C
for levels 0 through 5.

**Reasoning:**
Preheating is useful only if the house can store heat before a more expensive period.
Stopping all extra heat exactly at target wastes some of that thermal storage
opportunity. Allowing unlimited over-temperature would do the opposite: it could spend
cheap electricity on heat that is not needed and reduce comfort.

The saving level already expresses how strongly the user wants PumpSteer to trade
temperature variation for cost optimization, so the same intent should bound both the
lower comfort floor and the upper preheat allowance.

**Why taper instead of a hard switch:**
Below target, the full forecast-derived preheat boost is allowed. Between target and
`target + headroom`, the extra boost is reduced linearly. At the ceiling, extra boost
is zero. This avoids a sharp on/off transition around the upper temperature limit while
leaving the ordinary PI loop in control of baseline comfort.

---

### Why house thermal mass controls pre-brake lead time, not whether braking occurs

**Decision:** The house inertia slider affects ramp timing, not braking eligibility.

**Reasoning:**
- Price logic decides **if** a slot is expensive enough to brake
- House thermal mass decides **how early** the ramp must begin

A thermally heavy house starts pre-braking earlier to have the brake fully engaged when
the slot starts. A light house can wait longer and still reach the same state in time.

Letting thermal mass decide whether braking is active would mix plant dynamics with
price classification — harder to explain, harder to tune.

---

## Forecast and Thermal Model

### Why ThermalOutlook actively gates and scales preheat

**Decision:** Use `ThermalOutlook.preheat_worthwhile` to gate block 5b and
`preheat_strength` to scale the available boost whenever ThermalOutlook can be built.
Use the simpler cold-forecast heuristic only as a fallback.

**Reasoning:** A binary "cold/not cold" check throws away useful information about the
duration and strength of the coming cold period. ThermalOutlook already summarizes the
forecast into explainable attributes, so reusing those attributes avoids a second,
competing forecast interpretation.

This does not turn ThermalOutlook into a feedback controller. PI remains the comfort
loop, price still decides when an expensive period matters, and ThermalOutlook only
modulates the bounded preheat overlay.

---

### Why ThermalModel may fit automatically but not control braking yet

**Decision:** Collect cooling samples during braking and fit `thermal_k` after a
completed brake phase when at least 20 valid samples are available, but keep the fitted
model out of the active brake-depth decision for now.

**Reasoning:** Fitting the model is observational: it improves diagnostics without
changing heating behavior. Using a fitted model to reduce heat is a higher-risk step
because a poor fit could affect comfort.

The rollout order is therefore:

1. collect samples
2. fit and persist `thermal_k`
3. validate predicted temperature drop against real production data
4. expose diagnostic brake-safety information
5. only then consider bounded assistance to brake depth

The hard comfort floor remains authoritative regardless of any future model assistance.

---

## Output-path Safety

### Why Ohmigo Relay Guard is separate from PumpSteer control

**Decision:** Relay Guard may recover a configured physical Active/Bypass relay, but it
must not participate in PI, price classification, forecast decisions or virtual
temperature calculation.

**Reasoning:** These are different responsibilities:

```text
PumpSteer control → calculates virtual outdoor temperature
Ohmigo Push       → decides whether PumpSteer sends it
Relay Guard       → keeps the configured Active signal path available
```

Recovery is fail-closed: the guard acts only when it is armed, Ohmigo Push explicitly
reports on and the relay explicitly reports off. Unknown/unavailable state never causes
a command. A successful service call is not success until the relay itself reports on.

This separation also explains why `safe_mode` alone does not disable Relay Guard:
PumpSteer may still be forwarding the real outdoor temperature through the same physical
Active path.

---

## Summer Mode

### Why summer mode is the highest-priority control branch

**Decision:** After required input validation, summer mode short-circuits the remaining
control branches and passes through the real outdoor temperature unchanged.

**Reasoning:**
In summer, the heat pump may be in passive cooling or off entirely. Any fake temperature
offset — whether from PI, brake, or preheat — is meaningless or harmful. The heat
pump's own summer logic handles this correctly; PumpSteer should stay completely out
of the way.

Once required indoor/outdoor and price inputs have been validated, summer mode is
checked before PI, precool, brake and preheat decisions because those offsets are not
useful when the heat pump should be operating on its own summer logic.

Input validation still occurs first in the current implementation. Missing required
inputs can therefore enter `safe_mode` before the summer branch is reached.

---

## Comfort Floor

### Why comfort floor is indexed by aggressiveness, not a separate setting

**Decision:** `COMFORT_FLOOR_BY_AGGRESSIVENESS` is a fixed list indexed by the
aggressiveness slider (0–5), not a separate configurable value.

**Reasoning:**
Aggressiveness already expresses the user's intent about trading comfort for savings.
Coupling the comfort floor to aggressiveness makes behavior consistent with that intent.

Separating the two would create a configuration space where contradictory settings are
possible (e.g. high aggressiveness but a tight comfort floor that releases the brake
immediately). Coupling them prevents that confusion.

---

## HA Compatibility

### Why `get_forecasts` service call instead of `state_attr(..., 'forecast')`

**Decision:** Use `hass.services.async_call("weather", "get_forecasts", ...)`.

**Reason:** `state_attr(entity, 'forecast')` stopped working in HA 2026.2. The
forecast attribute was removed from entity state and is now only accessible via the
dedicated service call. The service call approach is forward-compatible.

---

### Why constants in `settings.py` require a full restart

**Decision:** Module-level `Final` constants are evaluated once at import time.

**Implication:** Changing a constant requires a full HA restart, not just a reload.
Integration reload re-instantiates the integration but does not re-import already-loaded
Python modules.

Most options are read from the current config entry on each update and take effect after
saving. Changing the configured Relay Guard relay is special: the integration reloads so
listeners can be rebuilt for the new relay entity.

---

### Why options are read via `cfg.get()` on every cycle

**Decision:** All tunable parameters are read from `config_entry.options` on each
`_do_update()` call.

**Reason:** Changes made via the options flow can be used on the next update without a
full Home Assistant restart. Reading current entry data also avoids stale cached values
when options change. Hardware-listener changes that require re-registration may still
trigger an integration reload.
