# PumpSteer Roadmap

## Current Version: 2.1.0 — Observability & Architecture

Version 2.1 builds on the stable 2.0 foundation by improving observability, making
forecast reasoning visible in the dashboard, and laying the groundwork for smarter
preheat decisions in future versions.

### Delivered in 2.0.x

- ✅ PI controller as primary control loop with integral windup protection
- ✅ Smooth brake ramping — no hard steps, dt capped at 60s
- ✅ Ramp timing derived from house thermal mass / house inertia
- ✅ P30/P80 price classification with stable daily thresholds
- ✅ Price thresholds cached per calendar day (prevents mid-slot reclassification)
- ✅ Pre-brake (block 5a) separated from preheat-boost (block 5b)
- ✅ `pre_braking` mode introduced to distinguish the two behaviors
- ✅ Comfort floor per aggressiveness level
- ✅ Brake hold time to prevent rapid cycling
- ✅ PI integral frozen (not decayed) during braking
- ✅ Ohmigo WiFi controller integration
- ✅ Notification system with mode-transition triggers
- ✅ Holiday mode
- ✅ Summer mode
- ✅ Safe mode fallback for missing sensor data
- ✅ HA 2026.2+ forecast API compatibility (`get_forecasts` service call)

### Delivered in 2.1.0

- ✅ `sensor.pumpsteer_thermal_outlook` — exposes forecast analysis as a dashboard-visible sensor
  (preheat worthwhile, preheat strength, warming/cooling trend, precool risk, night min / day max temp)
- ✅ Preheat boost exposed as `switch.pumpsteer_preheat_boost` — controllable from dashboard and automations
  (previously only configurable in the options flow)
- ✅ `ThermalModel` passive sample collection during braking sessions — groundwork for future thermal learning
- ✅ `forecast.py` refactored for clearer weather analysis and better separation of concerns
- ✅ Internal cleanup and refactoring for maintainability and future extensibility

---

## 🔴 Active / Near-term

### Connect ThermalOutlook to preheat-boost control (block 5b)
Replace the current `_forecast_is_cold()` heuristic with `ThermalOutlook.preheat_worthwhile`
so that block 5b uses the richer forecast analysis already computed by `ThermalOutlookSensor`.
This is the established implementation order: passive collection ✅ → connect ThermalOutlook → combine with ThermalModel once k is calibrated.

### Verify brake ramp end-to-end in production
Observe a full pre-brake cycle to confirm the dt-cap fix works correctly across an
entire ramp-in → braking → ramp-out sequence.

### Optional: clamp `factor` against `ideal_factor` in block 5a
Guard against dirty `_brake_ramp` state from restores or unexpected mode transitions.
Evaluate after observing the next production cycle.

---

## 🟡 Post-2.1 — Planned

### 1. Smarter preheat decisions
- Use `ThermalOutlook.preheat_strength` to scale the preheat boost proportionally
  rather than applying a fixed `PREHEAT_BOOST_C`
- Avoid preheat-boost when the cold period is too short to matter

### 2. Activate ThermalModel fitting
- Call `ThermalModel.fit()` once per day (at midnight alongside threshold refresh)
  once sufficient braking session data has accumulated
- Use fitted `k` to predict indoor temperature drop during planned brakes
- Expose `brake_safe` prediction as a sensor attribute for verification

### 3. Smarter price strategy
- Optional hybrid weighting between trailing history and today/tomorrow horizon
  (constants exist in `settings.py` but are not yet applied)
- Consider price spread within the day, not just absolute P80 threshold

### 4. Configuration improvements
- More user-friendly option labels
- Validate that sensor entity IDs exist on config entry setup

---

## 🟢 Future / Nice to Have

### 1. Adaptive PI tuning (limited scope)
- Semi-automatic Kp/Ki suggestion based on observed temperature response
- Must remain fully explainable and optional
- No automatic self-modification without user confirmation

### 2. Advanced forecast strategy
- Multi-hour price + temperature optimization
- Smarter thermal mass planning across consecutive expensive periods

### 3. Precool mode improvements
- Better lookahead and margin tuning for summer precooling

---

## ❌ Out of Scope (permanent)

- Machine learning control loops
- Black-box decision systems
- Any behavior that cannot be explained from its inputs alone
- Cloud dependencies

---

## Design Constraints (never compromise)

These constraints apply to all future development:

1. **PI is always the primary loop** — price and forecast are overlays only
2. **No double influence** — each signal affects the system once
3. **Brake is bounded** — comfort floor always takes precedence
4. **Thresholds are stable within a day** — no mid-slot reclassification
5. **PI integral is frozen during braking** — preserves thermal context for ramp-out
6. **Pre-brake is price-only** — never gated on forecast
7. **Preheat-boost is forecast-gated** — only when cold weather is actually coming
