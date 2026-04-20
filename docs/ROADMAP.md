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

## Current version

See the [Changelog](CHANGELOG) for details on what has been delivered.

---

## 🔴 Active / Near-term

### Connect ThermalOutlook to preheat-boost (block 5b)

Replace the current `_forecast_is_cold()` heuristic in block 5b with
`ThermalOutlook.preheat_worthwhile` from the thermal outlook sensor.

This gives preheat-boost access to the richer forecast analysis already computed by
`sensor.pumpsteer_thermal_outlook` — including warming trends, precool risk, and
night/day temperature splits — rather than the simpler cold-hours count.

Implementation order: passive collection ✅ → connect ThermalOutlook → combine with ThermalModel once k is calibrated.

### Activate preheat_strength scaling

Use `ThermalOutlook.preheat_strength` (0.0–1.0) to scale the preheat boost
proportionally rather than always applying the full `PREHEAT_BOOST_C = 4 °C`.
A cold forecast warrants a larger boost; a mildly cold forecast warrants less.

### Verify brake ramp end-to-end in production

Observe a full pre-brake cycle to confirm the dt-cap fix works correctly across an
entire ramp-in → braking → ramp-out sequence.

### Optional: clamp `factor` against `ideal_factor` in block 5a

Guard against dirty `_brake_ramp` state from restores or unexpected mode transitions.
Evaluate after observing the next production cycle.

---

## 🟡 Post-current — Planned

### Activate ThermalModel fitting

Call `ThermalModel.fit()` once per day (at midnight alongside threshold refresh)
once sufficient braking-session data has accumulated (minimum 20 samples).

Use the fitted cooling rate constant `k` to:
- Predict indoor temperature drop during planned brakes
- Expose `brake_safe` as a sensor attribute for dashboard verification
- Eventually gate or adjust brake depth based on predicted comfort impact

### Smarter price strategy

- Optional hybrid weighting between trailing 72-hour history and today/tomorrow horizon
  (constants exist in `settings.py` but are not yet applied)
- Consider price spread within the day, not just the absolute P80 threshold
- Peak filter improvements: configurable minimum spike duration

### Configuration improvements

- More user-friendly option labels in the options flow
- Validate sensor entity IDs exist at config entry setup (not only on first use)

---

## 🟢 Future / Nice to Have

### Adaptive PI tuning (limited scope)

Semi-automatic Kp/Ki suggestion based on observed temperature response.
Must remain fully explainable, optional, and require user confirmation before
any parameter is changed. No automatic self-modification.

### Advanced forecast strategy

Multi-hour price + temperature optimization. Smarter thermal mass planning across
consecutive expensive periods. Better lookahead for tight price windows.

### Precool mode improvements

Better lookahead and margin tuning for summer precooling. More accurate warm-period
detection that accounts for cloud cover and wind.

---

## ❌ Out of Scope (permanent)

These will not be implemented regardless of requests:

- Machine learning control loops
- Black-box decision systems
- Any behavior that cannot be fully explained from its inputs alone
- Cloud dependencies of any kind

---

## Design constraints (non-negotiable)

All future development must respect these constraints:

1. **PI is always the primary loop** — price and forecast are overlays only
2. **No double influence** — each signal affects the system exactly once
3. **Brake is bounded** — comfort floor always takes precedence
4. **Thresholds are stable within a day** — no mid-slot reclassification
5. **PI integral is frozen during braking** — preserves thermal context for ramp-out
6. **Pre-brake is price-only** — never gated on forecast
7. **Preheat-boost is forecast-gated** — only when cold weather is actually coming
