---
layout: default
title: Changelog
nav_order: 9
---

# 📋 Changelog

All notable changes are documented here.
Versions follow [Semantic Versioning](https://semver.org/).

---
## [3.0.0-alpha.5] — Active OhmOnWiFi test output

### Added

- An explicitly enabled MQTT output for OhmOnWiFi and OhmOnWiFiPlus test devices.
- The supervised comfort controller can now send a bounded virtual outdoor
  temperature followed by the relay watchdog command.
- Output diagnostics distinguish a command accepted by the MQTT broker from verified
  device feedback.

### Safety

- Active output requires a concrete per-device MQTT topic and explicit confirmation
  that the device watchdog has been enabled and physically tested.
- Startup, shutdown, stale or invalid critical sensors, controller failure, and output
  failure all request relay `OFF`, returning control to the physical outdoor sensor.
- MQTT commands use QoS 1 and are never retained.
- A write fault is latched against further `ON` commands until the entry is reloaded.
- Price classification and saving level still have no physical-control authority.
- This alpha does not claim device acknowledgement; it is intended only for a spare
  test installation until feedback topics have been verified on real hardware.

## [3.0.0-alpha.4] — Safe price classification preview

### Added

- Immutable UTC price intervals and validated price timelines.
- Deterministic nearest-rank classification for saving levels 1–5.
- Explicit results for disabled, missing, incomplete-period, unseparated-threshold, and
  classified price data.
- Coverage for negative prices, 15-minute markets, gaps, boundaries, variable slot
  counts, and real Stockholm 23/25-hour tariff days.

### Fixed

- Config-entry identity no longer changes conceptually when indoor or outdoor sensors
  are replaced in the options flow.
- Duplicate sensor pairs are rejected independently of the stable entry identity.
- Existing alpha.3 entries migrate to the new stable identity without changing their
  selected sensors or other options.
- English option-flow translations now match the integration strings.

### Safety

- The price preview cannot request heating, preheating, curtailment, or physical output.
- Price data errors remain separate from the comfort controller.
- No price provider is selected automatically in this alpha.

## [3.0.0-alpha.3] — Editable temperature sources

### Added

- Indoor and outdoor temperature sensors can be replaced through the Home Assistant
  Configure flow.
- Source changes reload V3 and reset incompatible learned evidence safely.

### Safety

- Source changes preserve shadow mode and cannot activate physical output.

## [3.0.0-alpha.2] — Saving-level shadow policy

### Added

- One Home Assistant `number.pumpsteer_saving_level` control from 0 to 5.
- Deterministic internal cheap/expensive percentile mapping.
- Shadow diagnostics for the selected level and derived price bands.

### Safety

- The setting has no price-planner or physical-control authority in this alpha.
- Level 0 disables price classification explicitly.
- Legacy ramp, inertia, and percentile number controls are not loaded by V3.

## [2.1.1] — Release hardening & beta output support

### Fixed
- Corrected HACS repository structure.
- Removed misplaced integration-level `hacs.json`.
- Updated manifest version to `2.1.1`.
- Improved CI validation with HACS, HASSFest, Ruff and Pytest.

### Improved
- Improved PumpSteer logging and telemetry.
- Improved notification handling.
- Improved Ohmigo push handling.
- Expanded documentation, installation guide, dashboard examples, tuning and troubleshooting.
- Improved internal architecture cleanup and maintainability.

### Added
- Experimental generic Modbus output support.
- PumpSteer can now push fake outdoor temperature directly via Home Assistant services.
- Adds groundwork for native non-Ohmigo output targets.
- Initial testing performed with Thermia Genesis / Calibra heat pumps.

---

## Beta feature: Thermia Genesis / Modbus output

PumpSteer 2.1.1 introduces experimental support for direct Modbus-based fake outdoor temperature control.

This allows compatible heat pumps to receive PumpSteer's calculated fake outdoor temperature without requiring Ohmigo hardware.

---

## [2.1.0] — Observability & Architecture

### Added
- **`sensor.pumpsteer_thermal_outlook`** — new sensor exposing PumpSteer's internal
  forecast analysis: preheat worthwhile, preheat strength, warming/cooling trends,
  night min / day max temperature, precool risk, and effective wind-chill temperature.
  Primarily diagnostic in 2.1.0 — does not yet replace core preheat logic.
- **`switch.pumpsteer_preheat_boost`** — preheat boost is now a proper dashboard switch.
  Previously only configurable via the options flow. Existing state is preserved across
  upgrades via RestoreEntity.
- **`ThermalModel`** in `thermal_model.py` — passively collects indoor cooling rate
  samples during braking periods. Foundation for future brake safety prediction.
  `fit()` is not yet called; this is passive collection only.

### Changed
- `forecast.py` refactored — cleaner weather analysis, better separation between
  forecast retrieval and thermal analysis. `ThermalOutlook` dataclass introduced.
- `thermal_model.py` introduced as a separate module for thermal regression logic.
- `ThermalOutlookSensor` suppresses `preheat_worthwhile` when
  `indoor_temp >= target_temperature` to avoid unnecessary preheat signals.
- Internal cleanup for maintainability and future extensibility.

### Notes
- No migration required. Fully backward compatible with 2.0.x.
- All new features are additive — existing behavior is unchanged.
- `ThermalModel.fit()` is identified as a future improvement; not called in 2.1.0.

---

## [2.0.x] — Stability & Hardening

### Fixed (across 2.0.x patch releases)
- Brake ramp `dt` now capped at 60 seconds per step — prevents large ramp jumps
  after HA restarts or long gaps between polling cycles.
- Midnight grace window (00:00–00:15) prevents stale price threshold caching before
  Nordpool delivers fresh data.
- P80 guard: if P80 for the day is below `ABSOLUTE_CHEAP_LIMIT`, all slots are
  classified as cheap — no braking on days when electricity is universally cheap.
- `_forecast_is_cold()` result correctly isolated from `bridge_short_dip` path.
- `ramp_in` computed against `PRICE_EXPENSIVE` when `upcoming=True` to ensure correct
  ramp duration regardless of intermediate price categories.

---

## [2.0.0] — The Big Rewrite

### Added
- **PI controller** as the primary control loop with integral windup protection
  (`PID_INTEGRAL_CLAMP`). Integral is frozen (not decayed or reset) during braking.
- **Smooth brake ramping** — `brake_factor` ramps in and out over configurable minutes.
  No hard steps.
- **P30/P80 price classification** with per-day caching. Prevents mid-slot
  reclassification from releasing the brake unexpectedly.
- **Pre-brake (block 5a)** — pure price signal, starts ramp before the expensive slot.
  Independent of forecast availability.
- **Preheat-boost (block 5b)** — forecast-gated, boosts heating before expensive
  periods when weather is cold.
- **`pre_braking` mode** — separate from `preheating` for unambiguous logging and
  dashboard state.
- **Comfort floor** per aggressiveness level — brake releases automatically when
  indoor temperature drops too far.
- **Brake hold time** — prevents oscillation during short cheap dips within a longer
  expensive block.
- **Summer mode** — passes through real outdoor temperature when outdoor temp exceeds
  threshold. Highest-priority check.
- **Safe mode** — passes through real outdoor temperature when any required sensor is
  missing or invalid.
- **Holiday mode** — lower target (16 °C default), same PI/braking logic. Scheduled
  via datetime helpers.
- **Ohmigo integration** — pushes fake temp to Ohmigo WiFi controller with hysteresis
  and rate limiting.
- **Notification system** — push alerts on mode transitions (braking / preheating).
- **HA 2026.2+ compatibility** — uses `weather.get_forecasts` service call instead of
  deprecated `state_attr(..., 'forecast')`.
- **Peak filter** — ignores expensive price spikes shorter than
  `PEAK_FILTER_MIN_DURATION_MINUTES` (default 30 min).

### Removed
- Machine learning features from v1.x
- `very_cheap`, `extreme` price categories — replaced with `cheap`, `normal`, `expensive`
- All cloud dependencies

### Breaking changes from 1.x
- All entity IDs renamed
- Price categories changed
- Options flow rebuilt
- Automations referencing old entities must be updated

---

## [1.x] — Legacy

Version 1.x used heuristic control with ML features and cloud-optional components.
No longer supported. See the [Installation Guide](INSTALLATION#upgrade-from-1x--2x)
for migration instructions.
