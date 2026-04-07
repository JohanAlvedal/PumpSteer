 PumpSteer Roadmap

## Current Version: 2.0.x — Stable

Version 2.0 delivered a stable, predictable, and well-architected control system.
The 2.0.x series continues with bug fixes and incremental hardening.

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

---

## 🔴 Active / Near-term

### Verify brake ramp fix end-to-end
Observe a full pre-brake cycle in production from the beginning to confirm the dt-cap
fix works correctly across an entire ramp-in → braking → ramp-out sequence.

### Optional: clamp `factor` against `ideal_factor` in block 5a
Guard against dirty `_brake_ramp` state from restores or unexpected mode transitions.
Discussed but not yet applied — evaluate after observing the next production cycle.

---

## 🟡 Post-2.0 — Planned

### 1. Improved forecast usage
- More precise preheat window timing based on forecast temperature profile
- Avoid preheat-boost triggering when the cold period is too short to matter

### 2. Smarter price strategy
- Optional future hybrid weighting between trailing history and today/tomorrow horizon
  (constants exist today, but this is not yet implemented)
- Peak filter: ignore expensive spikes shorter than a configurable threshold
  (already partially implemented via `PEAK_FILTER_MIN_DURATION_MINUTES`)
- Consider price spread within the day, not just absolute P80 threshold

### 3. Diagnostics & debugging
- Richer sensor attributes: PI P-term, I-term, brake factor, price category all visible
- Better mode transition logging
- Dashboard template sensors for capturing brake/price snapshots

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
