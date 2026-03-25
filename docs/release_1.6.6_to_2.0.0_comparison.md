# PumpSteer 1.6.6 → 2.0.0 Comparison and Migration Notes

## Part 1 — Executive Summary

PumpSteer 2.0.0 is a control-architecture rewrite compared to 1.6.6.

- **Core control changed from heuristic mode switching to PI + explicit state machine.**
  1.6.6 used `calculate_temperature_output(...)` and temperature/price heuristics; 2.0.0 uses `PIController` and explicit modes (`summer_mode`, `precool`, `preheating`, `braking`, `normal`, `holiday`, `safe_mode`).
- **Electricity handling changed from single-entity + dual model (`hybrid`/`percentiles`) to one standardized classifier (`cheap|normal|expensive`) over today+tomorrow price lists.**
- **Braking is now stateful and ramped**, with brake-hold and expensive-peak filtering, instead of immediate category-triggered brake behavior.
- **Entity model changed**: 2.0.0 introduces integration-owned Number/Switch/Datetime entities (target, aggressiveness, house inertia, holiday switch/dates), while 1.6.6 depended on fixed helper IDs from package YAML.

Largest migration risks:

1. Old automations matching legacy price labels (`very_cheap`, `very_expensive`, `extreme`, etc.) break logically.
2. Old setups with only current-price state and no `today/raw_today` + `tomorrow/raw_tomorrow` lists degrade or enter safe mode.
3. Holiday helper names/entity types changed (from `input_boolean/input_datetime` helpers to PumpSteer-owned `switch/datetime` entities).

## Part 2 — Detailed Version Comparison

### Compact comparison table

| Area | 1.6.6 | 2.0.0 | User impact |
|---|---|---|---|
| Core controller | Heuristic temperature logic (`calculate_temperature_output`) + mode heuristics | PI controller (`PIController`) + explicit state machine in sensor | Different runtime behavior and tuning expectations |
| Price classification | `hybrid` or `percentiles`; many categories | Standardized P30/P80 with `cheap/normal/expensive` | Existing category-based automations need rewrite |
| Price inputs | Primarily one price entity; today list | Today + tomorrow list model with fallback chaining | Sensors lacking structured attributes may fail |
| Braking | Immediate braking by high-price category and temp windows | Ramped braking, hold-time, comfort floor release, short-peak filter | More stable behavior, but different transitions |
| Forecast usage | CSV input_text forecast for precool checks | Weather entity forecast + price lookahead planning + preheat/precool decisions | Config and planning behavior changed |
| Holiday logic | Reads fixed helper IDs (`input_boolean.holiday_mode`, etc.) | Uses integration-owned switch/datetime entities and auto-activation/deactivation | Old holiday helpers are no longer control source |
| Integration entities | Single sensor + optional ML sensor modules | Sensor + Number + Switch + Datetime platforms | Dashboards/helpers need updates |
| ML/adaptive modules | Present (`ml_adaptive.py`, `ml_sensor.py`) | Removed from runtime path | Legacy ML cards/entities obsolete |

### A) Core functionality

#### What existed in 1.6.6

- Main sensor implemented in `custom_components/pumpsteer/sensor/sensor.py`.
- Heuristic temperature output via `temp_control_logic.calculate_temperature_output(...)`.
- Optional ML collector path (`ml_adaptive.py`) and separate ML sensor module (`sensor/ml_sensor.py`).
- Configured with fixed helper IDs (holiday, forecast, aggressiveness, house inertia, price model selector).

#### What exists in 2.0.0

- Main runtime sensor in `custom_components/pumpsteer/sensor.py`.
- PI-based control in `custom_components/pumpsteer/control.py`.
- Additional entity platforms: `number.py`, `switch.py`, `datetime.py`.
- Deterministic mode/state-machine control and safe-mode fallback.

#### New / removed / renamed

- **New**: PI terms and clamps exposed in options flow (`pid_kp`, `pid_ki`, `pid_kd`, integral/output clamp).
- **New**: Integration-owned Holiday switch and start/end datetime entities.
- **Removed**: ML modules from active code path (`ml_adaptive.py`, `sensor/ml_sensor.py`).
- **Removed/obsolete behavior**: runtime dependency on `input_select.pumpsteer_price_model`.
- **Mode naming** changed from `neutral/heating/braking_by_temp/braking_by_price/...` patterns to explicit state-machine modes (`normal`, `braking`, `preheating`, etc.).

### B) Control behavior

#### Strategy change

- **1.6.6**: Calculated fake outdoor temp directly from indoor-target error and aggressiveness using compensation factors.
- **2.0.0**: Computes demand via PI controller, then composes with braking/preheat ramps.

#### PI/PID details

- PI controller computes `error = target - indoor`, then uses `kp/ki/kd` with anti-windup clamp and output clamp.
- During braking, integral can be frozen (current implementation uses freeze) to avoid windup/jumps.

#### Feedforward / forecast influence

- No explicit feedforward use in current PI call path (`feedforward_bias=0.0`).
- Forecast now materially influences precool and preheat gating (cold/warm checks + upcoming expensive window logic).

#### Aggressiveness behavior

- **1.6.6**: Aggressiveness scaled direct heuristic heating/braking response.
- **2.0.0**: Aggressiveness primarily affects comfort floor tolerance and mode behavior (and `0` disables price logic, running pure PI).

#### Indoor protection

- **1.6.6**: Heating threshold and a dynamic “price brake window” prevented some price braking when too cold.
- **2.0.0**: Explicit comfort floor per aggressiveness (`COMFORT_FLOOR_BY_AGGRESSIVENESS`); if indoor drops below floor during expensive period, brake is released.

#### Fake outdoor temperature calculation

- **1.6.6**: Heuristic direct adjustment + hard brake caps (`BRAKE_FAKE_TEMP` or seasonal offset logic).
- **2.0.0**: `fake_temp = outdoor - pi_demand` in normal operation; in braking/preheat transitions it blends PI fake temp with brake target via ramp factor.

### C) Electricity price handling (critical)

#### 1.6.6

- Reads one price entity attributes (`today` or `raw_today`) and classifies using:
  - `percentiles` model (`classify_prices`), or
  - `hybrid` model (`async_hybrid_classify_with_history`) selected by `input_select.pumpsteer_price_model`.
- Rich categories including `very_cheap`, `very_expensive`, `extreme`, `negative_price`.

#### 2.0.0

- Reads **today and tomorrow** attributes:
  - today: `today` then `raw_today`
  - tomorrow entity: `tomorrow` then `raw_tomorrow`
  - fallback to tomorrow attrs on today entity
- Supports item formats: numeric, numeric string, dict with `value`/`price`.
- Thresholds computed as P30/P80 from recorder history (fallback to day prices), cached hourly.
- Categories are strictly `cheap`, `normal`, `expensive`.
- Applies short expensive-spike filtering (`filter_short_peaks`).

#### Why old setups may fail / drift

- If setup only had a current-state price sensor (without list attributes), 2.0.0 cannot build price timeline and can enter safe mode.
- If automations parse old category names, they no longer trigger correctly.
- If users still expect `hybrid` vs `percentiles` toggling behavior, control no longer follows that model.

### D) Braking logic

#### 1.6.6 braking triggers

- High-price categories (`expensive`, `very_expensive`, `extreme`) combined with temperature mode checks caused immediate `braking_by_price` or brake blocking.
- Also had `braking_by_temp` when indoor too warm relative to target.

#### 2.0.0 braking triggers

- Primary trigger: current classified slot is `expensive`.
- Braking ramps in/out over computed minutes based on inertia and category jump.
- Brake-hold keeps braking through short cheap dips.
- Comfort floor guard can force brake release when house gets too cold.
- Upcoming expensive periods can trigger preheat state before expensive slot.

#### Threshold and dynamics differences

- Shift from static/immediate category decisions to **stateful ramp + hold + peak filter**.
- Braking is now more dynamic and less twitchy, but requires correct price timeline and interval detection.

### E) Forecast and planning behavior

- **1.6.6**: Forecast mainly from `input_text.hourly_forecast_temperatures`, used for precool checks.
- **2.0.0**: Forecast builder merges weather forecast and price forecast context, and preheat decision checks upcoming expensive slots + cold-forecast window.
- Lookahead behavior is explicit (`PRICE_LOOKAHEAD_HOURS`, ramp windows, slot-based upcoming expensive detection).

### F) Configuration and integration setup

#### Required/selectable entities

- **1.6.6 config flow** requested indoor/outdoor/price entity and injected hardcoded helper IDs.
- **2.0.0 config/options flow** explicitly requests today and tomorrow price entities, optional weather entity, and PID tuning options.

#### Helper expectations

- **1.6.6** expected package helpers with fixed IDs (`input_number.house_inertia`, `input_boolean.holiday_mode`, etc.).
- **2.0.0** uses integration-owned entities discovered via entity registry (`number`, `switch`, `datetime` unique IDs per config entry).

#### Attributes vs state dependencies

- **Both** rely heavily on price attributes rather than state for future planning.
- **2.0.0** dependence is stricter because braking/preheat planning requires slot timeline and classification continuity.

## Part 3 — Breaking Changes / Migration Risks

### 1) Hard Breaking Changes

1. **Price category schema changed to `cheap|normal|expensive`.**
   - Why it matters: automations/templates using old strings stop matching.
   - Verify/update: replace category checks and dashboard badges.

2. **`price_tomorrow_entity` is required in flow/options.**
   - Why it matters: old single-entity assumptions may fail setup validation or degrade logic.
   - Verify/update: set tomorrow entity (or same entity if it exposes tomorrow attrs).

3. **Holiday control source changed.**
   - Why it matters: old `input_boolean.holiday_mode` + `input_datetime.*` are not the active runtime entities in 2.0.0 control path.
   - Verify/update: use PumpSteer-created Holiday switch + Holiday start/end datetime entities.

4. **ML sensor/runtime removed.**
   - Why it matters: old dashboards or automations targeting ML entities fail.
   - Verify/update: remove references to `sensor.pumpsteer_ml_analysis` and ML adaptive artifacts.

### 2) Soft Breaking Changes / Behavior Risks

1. **Only current price state is insufficient for new planning logic.**
   - Risk: system may run with poor planning or enter safe mode when no usable list data exists.
   - Verify: `today/raw_today` and `tomorrow/raw_tomorrow` contain numeric list data.

2. **Braking transitions now ramp/hold filtered.**
   - Risk: users expecting immediate brake release/engage perceive “lag” (intentional anti-flap behavior).
   - Verify: tune inertia, `BRAKE_HOLD_MINUTES`, and inspect `brake_factor` attribute.

3. **Aggressiveness semantics changed.**
   - Risk: same numeric aggressiveness gives different comfort/saving feel versus 1.6.6.
   - Verify: retune aggressiveness + PID settings and observe `comfort_floor_c` and `heating_demand_c`.

4. **Forecast source changed (weather entity path).**
   - Risk: users still updating old CSV helper only may not get full preheat/precool behavior if weather entity not configured.
   - Verify: configure `weather_entity` and confirm forecast availability in logs/attributes.

5. **Integration now uses internal number/switch/datetime entities.**
   - Risk: existing automations tied to old helper IDs silently stop affecting control.
   - Verify: repoint automations to PumpSteer entities linked to config-entry unique IDs.

## Part 4 — README / Migration Guide Draft

### What changed from 1.6.6 to 2.0.0

PumpSteer 2.0.0 introduces a new PI-based control core and a deterministic state machine (`summer_mode`, `precool`, `preheating`, `braking`, `normal`, `holiday`, `safe_mode`).

Compared with 1.6.6, which used heuristic temperature logic and optional hybrid/percentile price models, 2.0.0 standardizes electricity handling to one classifier (`cheap`, `normal`, `expensive`) based on P30/P80 thresholds and day-ahead price lists.

### Breaking changes

- Price category names changed (legacy categories removed).
- Price model selector (`input_select.pumpsteer_price_model`) is obsolete in runtime behavior.
- Configuration now expects both `electricity_price_entity` and `price_tomorrow_entity`.
- Holiday helpers changed to PumpSteer-owned switch/datetime entities.
- Legacy ML sensor modules and dependent UI/automation assumptions are removed.

### Electricity price sensor changes

PumpSteer now expects structured list attributes for price planning:

- Today prices from `today` or `raw_today`.
- Tomorrow prices from `tomorrow` or `raw_tomorrow` (from dedicated tomorrow entity or fallback on today entity).

Supported list item formats:

- numeric (`0.95`)
- numeric string (`"0.95"`)
- dict (`{"value": 0.95}` or `{"price": 0.95}`)

If no usable list data is available, PumpSteer cannot build category timelines and may enter safe mode.

### How braking works now

Braking is no longer a simple immediate switch. In 2.0.0 it is stateful:

1. Expensive slots request brake.
2. Brake ramps in/out over time based on inertia and price-category jump.
3. Short expensive spikes are filtered to reduce flapping.
4. Brake hold keeps braking across short cheap dips.
5. Comfort floor protection can release brake if indoor temperature becomes too low.

### Upgrade checklist

1. Update integration and open PumpSteer options.
2. Confirm indoor, outdoor, today price, tomorrow price, and optional weather entities are valid.
3. Verify today/tomorrow price attributes contain numeric list data.
4. Replace all automation/template checks using old price categories.
5. Remove obsolete ML sensor cards/entities.
6. Repoint holiday automations to PumpSteer Holiday switch/datetime entities.
7. Verify runtime attributes: `mode`, `price_category`, `p30`, `p80`, `brake_factor`, `status`.
8. Test one expensive period to confirm preheat/brake transitions and comfort floor behavior.

## Part 6 — Installation & Upgrade Guides

### Section A — Fresh Installation (PumpSteer 2.0.0)

This guide is for users who are **not** upgrading from older PumpSteer versions.

#### Step 1: Install PumpSteer

- Preferred: Install via HACS custom repository (`https://github.com/JohanAlvedal/PumpSteer`).
- Alternative: Manual copy of `custom_components/pumpsteer` into your Home Assistant config.

#### Step 2: Restart Home Assistant

- Fully restart Home Assistant after installation.
- Do not continue setup before restart is complete.

#### Step 3: Add integration in UI

- Go to **Settings → Devices & Services → Add Integration → PumpSteer**.

#### Step 4: Select required entities during config flow

Required:

1. Indoor temperature sensor (`indoor_temp_entity`)
2. Outdoor temperature sensor (`real_outdoor_entity`)
3. Electricity price entity for today/current (`electricity_price_entity`)
4. Electricity price entity for tomorrow (`price_tomorrow_entity`)

Optional but recommended:

5. Weather entity (`weather_entity`) for forecast-aware preheat/precool logic

#### Step 5: Understand what PumpSteer creates automatically

After setup, PumpSteer creates integration-owned entities:

- **Number entities**
  - Target Temperature
  - Summer Mode Threshold
  - Saving Level (aggressiveness)
  - House Thermal Mass (inertia)
- **Switch entity**
  - Holiday Mode
- **Datetime entities**
  - Holiday Start
  - Holiday End

These entities belong to the PumpSteer config entry and should be used in automations instead of old helper assumptions.

#### Step 6: Verify price sensor format (critical)

Your selected price entities must expose day-ahead list attributes:

- Today list from `today` or `raw_today`
- Tomorrow list from `tomorrow` or `raw_tomorrow`

Accepted list item formats:

- Numeric: `0.95`
- Numeric string: `"0.95"`
- Dict item: `{"value": 0.95}` or `{"price": 0.95}`

If these lists are missing or non-numeric, PumpSteer cannot classify and plan correctly.

#### Step 7: First validation checklist

After 10–30 minutes of runtime, verify:

- `sensor.pumpsteer` has numeric state updates.
- Attribute `status` is `ok` (not safe mode).
- Attribute `price_category` changes between `cheap|normal|expensive` over the day.
- Attributes `p30` and `p80` are present and finite.
- Attribute `mode` changes logically with conditions.
- During expensive periods, `brake_factor` can rise above 0.

If validation fails, first inspect price attributes and selected entities in options flow.

---

### Section B — Upgrade Guide (1.6.6 → 2.0.0)

This guide is for existing 1.6.6 users. Follow in order.

#### 1) Before upgrading

Checklist before touching files:

- Export/backup Home Assistant config.
- Document current PumpSteer automations and dashboard cards.
- List every reference to old entities, especially:
  - `input_select.pumpsteer_price_model`
  - `input_boolean.holiday_mode`
  - `input_datetime.holiday_start`
  - `input_datetime.holiday_end`
  - ML sensor cards/templates
- Check what your price sensor actually exposes (`today/raw_today`, `tomorrow/raw_tomorrow`).

#### 2) What will NOT carry over (or should be considered deprecated)

These old assumptions should be treated as non-valid in 2.0.0 runtime behavior:

- Legacy price categories (`very_cheap`, `very_expensive`, `extreme`, `negative_price`).
- ML runtime/sensor expectations from 1.6.6.
- `input_select.pumpsteer_price_model` behavior (hybrid vs percentile switch).
- Old holiday helper naming model as primary control source.

#### 3) What MUST be reconfigured

Must-do migration actions:

1. Configure/verify both price entities:
   - today/current price entity
   - tomorrow price entity
2. Update automations/templates to `cheap|normal|expensive` categories.
3. Update dashboards/cards that reference removed ML outputs.
4. Repoint holiday automations to PumpSteer-created Holiday switch/datetime entities.

#### 4) What MAY still work but must be verified

- Existing indoor/outdoor sensors (usually reusable).
- Aggressiveness setting value (same range, different behavior impact).
- Forecast-related behavior (especially if you depended on old helper-only approach).
- Any template reading old attribute names or expecting old mode names.

#### 5) Step-by-step upgrade process

1. Upgrade PumpSteer files/version.
2. Restart Home Assistant.
3. Open PumpSteer config/options UI.
4. Re-select/confirm:
   - indoor temp
   - outdoor temp
   - electricity price (today)
   - electricity price (tomorrow)
   - optional weather entity
5. Verify that PumpSteer Number/Switch/Datetime entities exist.
6. Replace legacy automation conditions on old price categories.
7. Remove/replace legacy ML cards and entities.
8. Save and monitor one full price cycle.

#### 6) Post-upgrade validation checklist

- `sensor.pumpsteer` status is `ok`.
- Price classification transitions happen (`cheap|normal|expensive`).
- Braking appears during expensive blocks (check `mode=braking` and `brake_factor`).
- No persistent `safe_mode` unless input is truly missing.
- Holiday switch/datetime works and toggles expected behavior.
- Expected transitions appear: `normal`, `preheating`, `braking`, `precool`, `summer_mode` when conditions match.

#### 7) Common upgrade issues (real-world)

##### Issue: "PumpSteer stuck in safe mode"

- Likely cause:
  - Missing/invalid selected indoor/outdoor entity
  - No usable price list data
- Fix:
  1. Re-open options flow and re-select entities
  2. Confirm price attributes contain numeric list values
  3. Check `status` attribute reason text

##### Issue: "No braking happening"

- Likely cause:
  - Current slot not classified as `expensive`
  - Comfort floor protection is releasing brake
  - Price spikes filtered as too short
- Fix:
  1. Inspect `price_category`, `comfort_floor_c`, `brake_factor`
  2. Verify price interval/list continuity
  3. Validate aggressiveness and temperature conditions

##### Issue: "Wrong price category"

- Likely cause:
  - Unexpected price list format or bad numeric conversion
  - Thresholds affected by history/fallback data quality
- Fix:
  1. Inspect raw `today/raw_today` and `tomorrow/raw_tomorrow`
  2. Confirm entries are parseable as numeric values
  3. Verify `p30` and `p80` attributes are sane

##### Issue: "Holiday mode not working"

- Likely cause:
  - Automation still targets old helper entities
  - Start/end datetime invalid or not set
- Fix:
  1. Use PumpSteer Holiday switch + Holiday Start/End entities
  2. Ensure start < end and values are valid datetimes

##### Issue: "Automations not triggering"

- Likely cause:
  - Conditions still keyed on removed categories or removed ML entities
- Fix:
  1. Update triggers/conditions to current attributes and categories
  2. Test with Developer Tools → States to verify live values
