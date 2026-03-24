# PumpSteer

PumpSteer is a Home Assistant custom integration that shifts heat pump demand over time by publishing a **virtual outdoor temperature** (`sensor.pumpsteer`). It uses indoor temperature, outdoor temperature, dynamic electricity prices, and short weather forecast input to reduce cost while keeping comfort within configurable limits.

<a href="https://www.buymeacoffee.com/alvjo" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px !important;width: 200px !important;">
</a>

<a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=https%3A%2F%2Fgithub.com%2FJohanAlvedal%2FPumpSteer%2Ftree%2Fmain" target="_blank" rel="noreferrer noopener"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up a new integration." /></a>

---

## Overview

PumpSteer 2.0.0 is a control rewrite with a PI-based core controller and a simpler price model. The integration now focuses on one production sensor (`sensor.pumpsteer`) and deterministic state-machine behavior:

- `summer_mode`
- `precool`
- `preheating`
- `braking`
- `normal`
- `holiday`
- `safe_mode`

If required inputs are missing or invalid, PumpSteer enters **safe mode** and passes through the real outdoor temperature.

---

## Features (2.0.0)

- PI controller with configurable `Kp`, `Ki`, `Kd`, integral clamp, and output clamp.
- Dynamic price classification using **P30/P80** thresholds from recorder history (default trailing window: 72h).
- Expensive-price braking with ramp-in / ramp-out and brake-hold protection to avoid rapid toggling.
- Comfort floor logic tied to aggressiveness (0–5) to prevent over-braking when indoor temp is too low.
- Preheating logic when expensive periods are approaching and forecast indicates cold conditions.
- Precool logic when upcoming forecast exceeds summer threshold + margin.
- Holiday automation integration (`input_boolean` + start/end `input_datetime`) with auto-activation/deactivation.
- Support for hourly or sub-hourly price lists (interval auto-detection from timestamps/slot count).
- Built-in safe fallback behavior for missing sensors/prices.

---

## What’s New in 2.0.0

- Major control architecture change: old heuristic temperature logic replaced by PI + state-machine flow.
- Price categories simplified from multi-level legacy classes to three classes: `cheap`, `normal`, `expensive`.
- New two-entity price input pattern (`today` + `tomorrow`) in config/options flow.
- Price thresholding now standardized on recorder-backed percentiles (P30/P80) with caching.
- Short expensive spikes are filtered (minimum expensive duration handling).
- Legacy ML/adaptive session sensors and related outputs removed from the active runtime path.

---

## Version 1.6.6 → 2.0.0

In 1.6.6, PumpSteer used a mixed model with:

- optional `hybrid` classification against trailing average,
- optional percentile classification,
- richer category names (`very_cheap`, `very_expensive`, `extreme`, etc.),
- older temp heuristics (`calculate_temperature_output`) and neutral/heating/braking-by-temp modes,
- additional ML sensor modules in the integration package.

In 2.0.0, PumpSteer now:

- uses one consistent P30/P80 category model,
- runs PI-driven control with explicit operating states,
- uses explicit today/tomorrow price entity configuration,
- removes runtime dependence on legacy ML sensors and legacy price-model switch helpers.

---

## ⚠️ Breaking Changes

1. **Price category schema changed**
   - Old automations/templates expecting `very_cheap`, `very_expensive`, `extreme`, or `negative_price` will no longer match.
   - New categories are only: `cheap`, `normal`, `expensive`.

2. **Price model selector is no longer used**
   - `input_select.pumpsteer_price_model` (hybrid/percentiles) is no longer read by control logic.
   - Keeping it does nothing in 2.0.0.

3. **Two price entities are now part of configuration flow**
   - You must provide both:
     - `electricity_price_entity` (today/current source)
     - `price_tomorrow_entity` (tomorrow source; can point to same entity if it exposes both attributes)

4. **Legacy holiday helper names changed**
   - 2.0.0 uses:
     - `input_boolean.pumpsteer_holiday_mode`
     - `input_datetime.pumpsteer_holiday_start`
     - `input_datetime.pumpsteer_holiday_end`
   - Older names such as `input_boolean.holiday_mode` / `input_datetime.holiday_start` / `input_datetime.holiday_end` are not used by current logic.

5. **Legacy ML sensor expectations are invalid**
   - Documentation/UI cards relying on `sensor.pumpsteer_ml_analysis` from 1.6.6 should be removed or rewritten.

---

## Electricity Price Handling (IMPORTANT)

### 1.6.6 behavior (legacy)

- Primary input was typically one price entity.
- Classification could run in two modes:
  - `hybrid` (relative to trailing average + absolute cheap override), or
  - `percentiles` (multi-threshold).
- Categories could include values like:
  - `very_cheap`, `cheap`, `normal`, `expensive`, `very_expensive`, `extreme`, `negative_price`.
- The `input_select.pumpsteer_price_model` helper influenced behavior.

### 2.0.0 behavior (current)

PumpSteer expects **structured day-ahead lists** from entity attributes:

- **Today entity** (`electricity_price_entity`):
  - reads `today` first, then `raw_today` fallback.
- **Tomorrow entity** (`price_tomorrow_entity`):
  - reads `tomorrow`, then `raw_tomorrow`.
  - if empty, PumpSteer also checks tomorrow attributes on the today entity as fallback.

Accepted item formats in these lists:

- number (`0.95`)
- string (`"0.95"`)
- dict with price field (`{"value": 0.95}` or `{"price": 0.95}`)

Invalid/non-numeric entries are skipped.

### Forecast prices and lookahead

Yes, 2.0.0 uses future price slots from today+tomorrow lists for:

- upcoming expensive detection,
- preheating timing,
- braking ramp planning.

### Classification in 2.0.0

- Thresholds are computed as:
  - `p30` = 30th percentile
  - `p80` = 80th percentile
- Source for thresholds:
  1. recorder history from trailing 72h (if enough samples), else
  2. fallback to current day prices.
- Rule:
  - `cheap` if `price <= p30` **or** `price <= ABSOLUTE_CHEAP_LIMIT` (0.60)
  - `normal` if `price <= p80`
  - `expensive` otherwise
- Expensive spikes shorter than configured minimum duration are smoothed out.

### What you must change when upgrading

- Verify your selected entities expose **attribute lists**, not only a single state value.
- Configure `price_tomorrow_entity` in options/config flow.
- Update any automation/template that checks old category strings.
- Remove dependence on `input_select.pumpsteer_price_model`.

### What breaks if old setup is kept

- Old category-based automations stop triggering correctly.
- If tomorrow data is missing and today data is incomplete, control quality degrades or safe mode can trigger due to missing usable price data.
- Old “hybrid vs percentiles” expectations no longer reflect real control behavior.

### Why this redesign was made

The 2.0.0 implementation standardizes classification and control flow to reduce ambiguity and make behavior more deterministic, testable, and easier to reason about in production.

---

## Installation

### HACS (custom repository)

1. Go to **HACS → ⋮ → Custom repositories**.
2. Add repository URL: `https://github.com/JohanAlvedal/PumpSteer`.
3. Category: **Integration**.
4. Install PumpSteer.
5. Restart Home Assistant.
6. Add integration and select required entities.

---

## Configuration

### Entities selected in config flow

- `indoor_temp_entity` (sensor, temperature)
- `real_outdoor_entity` (sensor, temperature)
- `electricity_price_entity` (sensor with `today`/`raw_today` attributes)
- `price_tomorrow_entity` (sensor with `tomorrow`/`raw_tomorrow` attributes)

### Package/helper entities used by logic

PumpSteer 2.0.0 reads these fixed helpers:

- `input_number.indoor_target_temperature`
- `input_number.pumpsteer_summer_threshold`
- `input_number.pumpsteer_aggressiveness`
- `input_number.pumpsteer_house_inertia`
- `input_text.hourly_forecast_temperatures` (comma-separated temps)
- `input_boolean.pumpsteer_holiday_mode`
- `input_datetime.pumpsteer_holiday_start`
- `input_datetime.pumpsteer_holiday_end`

### Forecast format

`input_text.hourly_forecast_temperatures` should contain comma-separated numeric temperatures, for example:

```text
-5.0,-4.7,-4.1,-3.6,-3.2,-2.8,-2.1,-1.5
```

PumpSteer parses up to the configured lookahead window and ignores invalid/out-of-range values.

---

## Migration Guide (FROM 1.6.6)

### You can keep

- Indoor temperature sensor
- Outdoor temperature sensor
- Existing target/summer/aggressiveness helpers (if entity IDs still match current names)
- Existing forecast automation concept (writing CSV temps to input_text)

### You MUST change

1. **Price config**
   - Add/verify `price_tomorrow_entity`.
   - Ensure chosen sensors expose correct list attributes.

2. **Automations/templates**
   - Replace old price categories with `cheap|normal|expensive`.

3. **Holiday helper names**
   - Move to `pumpsteer_holiday_mode`, `pumpsteer_holiday_start`, `pumpsteer_holiday_end` names.

4. **Remove obsolete helpers from logic assumptions**
   - `input_select.pumpsteer_price_model` is obsolete in runtime behavior.

5. **UI cleanup**
   - Remove cards/entities expecting ML analysis sensors from old versions.

### Post-upgrade verification checklist

- `sensor.pumpsteer` has state and `status: ok`.
- Attribute `mode` changes logically over day conditions.
- Attributes `p30` and `p80` are present and finite.
- `price_category` changes between cheap/normal/expensive through the day.
- During missing input simulation, safe mode engages and passes through outdoor temp.
- Holiday mode toggles correctly using the new helper entity IDs.

---

## Troubleshooting

### `sensor.pumpsteer` unavailable or safe mode

- Check selected indoor/outdoor sensors are available.
- Check price entities expose list attributes (`today`/`tomorrow` or `raw_*`).
- Verify numeric data in those lists.

### Price category looks wrong

- Confirm recorder has enough recent history (ideally at least 72h retained).
- Validate unit/scale consistency from your price integration.
- Remember categories are percentile-based and relative to recent data.

### No preheating / unexpected preheating

- Verify forecast input text is valid numeric CSV.
- Check `summer_threshold`, aggressiveness, and lookahead conditions.
- Understand that preheating in 2.0.0 is tied to upcoming expensive slots plus cold-forecast condition.

### Holiday mode not activating

- Use `input_boolean.pumpsteer_holiday_mode` and the two `pumpsteer_holiday_*` datetime helpers.
- Ensure end time is after start time.

---

## Optional: Architecture / Logic Notes

Control order in 2.0.0 (high-level):

1. Validate required data; otherwise `safe_mode`.
2. Evaluate holiday target override.
3. Parse and classify combined today+tomorrow prices.
4. Apply mode priority:
   - summer
   - precool
   - aggressiveness=0 (pure PI)
   - expensive-period braking
   - preheating before expensive blocks
   - normal PI / holiday PI
5. Publish resulting fake outdoor temperature and diagnostic attributes.

---

## Disclaimer

You use this integration at your own risk. Heating is a critical home system. Always monitor indoor comfort and system behavior after installation or migration.
