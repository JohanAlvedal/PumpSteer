---
layout: default
title: Roadmap
nav_order: 7
---

# 🗺 Roadmap
{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Current release line: 2.2.x

PumpSteer 2.2.x builds on the PI-first 2.0 architecture with stronger comfort
protection, forecast-aware preheating, clearer brake-state observability and more
resilient Ohmigo output handling.

See the [Changelog](CHANGELOG) for release-by-release details.

### Delivered in 2.2.x

- ✅ Pre-brake respects the same comfort floor as active price braking
- ✅ Short price dips are bridged only within `brake_hold_minutes`
- ✅ Explicit `brake_hold` operating mode and bridge transition logging
- ✅ ThermalOutlook gates preheat when available, with cold-forecast fallback
- ✅ `preheat_strength` scales the preheat boost
- ✅ Saving-level-based thermal headroom with tapered preheat near the ceiling
- ✅ ThermalModel fits `k` after a completed brake phase when at least 20 valid samples exist
- ✅ Fitted ThermalModel state is restored across Home Assistant restarts
- ✅ DST-safe electricity price slot indexing
- ✅ Optional Ohmigo Relay Guard with bounded retries and state verification
- ✅ Braking notifications include the exact current-slot price used by the control decision
- ✅ `current_price` and `current_price_unit` exposed for diagnostics
- ✅ Entity validation in setup/options flows for configured Home Assistant entities

---

## 🔴 Active / Near-term

### 1. Keep comfort regulation active when price data is unavailable

Today, missing price data enters safe mode and passes through the real outdoor
temperature. Review whether PumpSteer can instead keep the normal PI comfort loop
running while disabling only price-dependent overlays.

The desired fail-safe principle is:

- missing indoor/outdoor temperature → safe passthrough
- missing price data → no price optimization, but comfort regulation can continue
- missing weather forecast → no forecast-based preheat; price-only pre-brake remains available

This change must remain explicit and easy to diagnose.

### 2. Review preheat → pre-brake transition

Verify how stored thermal reserve is handled when PumpSteer has preheated the house
and then enters the pre-brake window before the expensive period.

Goals:

- avoid unnecessary heat immediately before braking
- avoid throwing away useful thermal reserve
- keep the PI loop as the baseline comfort controller
- preserve the strict separation between forecast-driven preheat and price-only pre-brake

### 3. Make preheat ramp timing use measured elapsed time

The brake ramp already advances from measured elapsed time with a capped `dt`.
The preheat ramp still advances by a fixed amount per update cycle.

Move preheat ramping to elapsed-time-based progression so behavior remains stable
across delayed polls, reloads and different update intervals.

### 4. Validate ThermalModel in production

ThermalModel fitting is already active, but it does not yet control brake depth.

Next validation step:

- observe fitted `thermal_k` over real brake sessions
- expose predicted temperature drop for planned brakes
- expose a diagnostic `brake_safe` result
- compare predictions with actual indoor temperature response

Only after production validation should ThermalModel be considered for bounded
assistance to brake depth.

### 5. Production validation of 2.2.x transitions

Continue observing complete real-world cycles:

`preheating → pre_braking → braking → brake_hold/ramp-out → normal`

Also verify Ohmigo Relay Guard behavior around reconnects and Home Assistant restarts.

---

## 🟡 Planned

### Smarter price strategy

- Optional hybrid weighting between trailing history and today/tomorrow horizon
  (constants exist in `settings.py` but are not currently applied)
- Consider price spread and block structure, not only the absolute P80 boundary
- Make peak-filter minimum duration configurable if production data shows a need

### ThermalModel-assisted braking

After diagnostic validation:

- use predicted indoor drop to describe brake safety
- consider bounded brake-depth adjustment before the comfort floor is reached
- never allow the model to override the hard comfort floor
- keep the decision fully explainable from current inputs and fitted `k`

### Configuration and UX improvements

- Continue simplifying user-facing option labels and descriptions
- Keep advanced constants out of the normal UI unless they have a clear user benefit
- Improve diagnostics before adding new tuning controls

---

## 🟢 Future / Nice to Have

### Adaptive PI tuning (limited scope)

Semi-automatic Kp/Ki suggestions based on observed temperature response.
Suggestions must remain explainable, optional, and require user confirmation before
any parameter is changed. No automatic self-modification.

### Advanced forecast strategy

Multi-hour price + temperature optimization with smarter use of thermal reserve
across consecutive expensive periods, while retaining the existing PI-first state
machine.

### Precool improvements

Improve summer precooling lookahead and margins. Evaluate whether forecast duration,
cloud cover and wind materially improve decisions before adding complexity.

---

## ❌ Out of Scope (permanent)

- Machine-learning control loops
- Black-box decision systems
- Any behavior that cannot be explained from its inputs alone
- Cloud dependencies

---

## Design constraints (non-negotiable)

1. **PI is always the primary loop** — price and forecast are overlays only
2. **No double influence** — each signal affects the system exactly once
3. **Brake is bounded** — comfort floor always takes precedence
4. **Thresholds are stable within a day** — no mid-slot reclassification
5. **PI integral is frozen during braking** — preserves thermal context for ramp-out
6. **Pre-brake is price-only** — never gated on forecast
7. **Preheat-boost is forecast-gated** — only when forecast context supports it
8. **Optional hardware recovery stays outside the control loop** — Relay Guard must not alter PI, price or thermal decisions
