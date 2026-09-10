# PumpSteer V3 Architecture

## Architectural boundary

V3 uses a pure, deterministic domain core. Home Assistant supplies observations and
delivers decisions, but no entity, service call, registry lookup, or persistence API
belongs inside the controller.

The central contract is:

```python
decision, next_state = controller.step(
    observation=observation,
    forecasts=forecasts,
    model=model,
    policy=policy,
    previous_state=state,
)
```

For identical inputs and state, this function shall return identical outputs and
state. Simulation, replay, shadow mode, and active control use this same function.

## Processing pipeline

```text
Home Assistant sources
    -> source adapters and validation
    -> normalized Observation and ForecastSeries
    -> capability and safety supervisor
    -> comfort controller
    -> bounded planner
    -> actuator model and output supervisor
    -> ControlDecision
    -> shadow or physical output adapter
```

Price and weather are optional capabilities. Safety validation is not optional. The
planner may constrain or bias the comfort request, but it may not bypass the output
supervisor or violate the safety policy.

## Domain types

The domain layer shall use immutable typed structures, including:

- `SensorReading`: value, observation timestamp, ingestion timestamp, source, and
  quality flags.
- `Observation`: indoor temperature, outdoor temperature, target, optional heat-system
  measurements, and current actuator feedback.
- `ForecastPoint` and `ForecastSeries`: timezone-aware timestamps, interval boundaries,
  value, source, and quality.
- `BuildingModel`: thermal parameters, uncertainty, fit metadata, and validity domain.
- `ActuatorModel`: delay, local gain, saturation, operating domain, and uncertainty.
- `ComfortPolicy` and `SafetyPolicy`: product-owned constraints.
- `ControlState`: controller, ramp, supervisor, and learning state required by the next
  step.
- `ControlDecision`: requested and supervised output, mode, reasons, active constraints,
  confidence, and model version.

Wall-clock access shall be injected. Domain code shall not call `now()`.

## Units and sign convention

Internal time is timezone-aware UTC. Durations are explicit seconds. Local time is
used only for presentation and tariff calendar rules.

| Quantity | Canonical name | Unit | Positive direction |
|---|---|---:|---|
| Indoor temperature | `indoor_temperature_c` | degC | Warmer |
| Outdoor temperature | `outdoor_temperature_c` | degC | Warmer |
| Target temperature | `target_temperature_c` | degC | Warmer |
| Comfort error | `comfort_error_c` | K | `target - indoor`; more heat required |
| Heating request | `heating_request_c` | K | More heating |
| Curtailment request | `curtailment_request_c` | K | Less heating |
| Virtual outdoor temperature | `virtual_outdoor_temperature_c` | degC | Warmer signal, normally less heating |
| Heating power | `heating_power_kw` | kW | Heat delivered to building |
| Indoor rate | `indoor_rate_c_per_hour` | K/h | Indoor temperature rising |
| Import price | `import_price_per_kwh` | currency/kWh | More expensive |

The output composition is always:

```text
virtual_outdoor_temperature_c =
    outdoor_temperature_c
    - heating_request_c
    + curtailment_request_c
```

Both requests are non-negative. Saturation, slew limiting, and hardware quantization
are applied afterward by the output supervisor. Modules shall not hide sign changes.

## State and reason model

Operating state and learning authority are separate dimensions. A controller may be in
`comfort` mode while the model is `observing` or `validated`.

Required operating modes:

- `passthrough`
- `comfort`
- `preheat`
- `curtail`
- `recovery`
- `summer_passthrough`
- `degraded`
- `failsafe`
- `shadow`

Transitions are driven by events and guards, not by scattered early returns. Every
decision contains one primary stable reason code and zero or more contributing reason
codes. Initial reason families include:

- `COMFORT_BELOW_TARGET`
- `COMFORT_WITHIN_BAND`
- `PREDICTED_COMFORT_RISK`
- `PRICE_SHIFT_BENEFICIAL`
- `MODEL_AUTHORITY_INSUFFICIENT`
- `OPTIONAL_FORECAST_MISSING`
- `CRITICAL_SENSOR_INVALID`
- `CRITICAL_SENSOR_STALE`
- `OUTPUT_RATE_LIMITED`
- `OUTPUT_SATURATED`
- `MODEL_OUTSIDE_VALID_DOMAIN`
- `INTERNAL_FAILSAFE`

Human-readable text is derived from reason codes and structured context; it is not the
control contract.

## Control hierarchy

1. The safety supervisor determines available capability and hard constraints.
2. The comfort controller produces a heating request from measured comfort error.
3. The building model predicts temperature and recovery trajectories with uncertainty.
4. The planner proposes bounded preheat or curtailment only when confidence and comfort
   margins permit it.
5. The output supervisor composes, clamps, rate-limits, and validates the virtual
   temperature.
6. The adapter either records the shadow decision or writes the supervised output.

The initial comfort controller may be PI-based. It shall implement anti-windup for both
planner intervention and actuator saturation. The architecture shall not assume that PI
is the only possible future explainable comfort controller.

### Economy preference

V3 exposes one integer saving level instead of percentile, ramp, and brake controls.
It maps deterministically to classification intent:

| Level | Cheap band | Expensive band |
|---:|---:|---:|
| 0 | Disabled | Disabled |
| 1 | <= P20 | >= P90 |
| 2 | <= P25 | >= P85 |
| 3 | <= P30 | >= P80 |
| 4 | <= P35 | >= P70 |
| 5 | <= P40 | >= P60 |

The level changes when price shifting may be considered, never how much thermal risk is
permitted. The learned validity domain, comfort budget, recovery guard, and output
supervisor remain independent upper bounds. Until the price planner is validated, the
Home Assistant number and its diagnostics are shadow-only.

### Price classification preview

Alpha.4 introduces a pure preview between the saving-level policy and any future
planner. The adapter must supply the exact UTC boundaries of one deterministic
comparison period; the core will not infer a period from whichever points happen to be
available. The future HA adapter will define which tariff day supplies those boundaries.
The preview uses the deterministic nearest-rank method
(`rank = ceil(percentile * sample_count / 100)`). Intervals may be hourly, 15 minutes,
or another explicit positive duration; the implementation assumes neither 24 hours nor
96 slots per day.

One classification timeline must use one provider identity, SEK/kWh, and one interval
duration. Mixed 60- and 15-minute input is rejected until a time-weighted method is
specified; otherwise quarter-hour periods would receive disproportionate weight.

The preview reports `disabled`, `unavailable`, `uninformative`, or `classified` with a
stable reason code. A missing current interval is never filled from a neighbouring
price. Unseparated thresholds are `uninformative`, negative prices are valid, and
threshold boundaries are inclusive. `ShadowPricePlan` always denies physical control,
preheat, and curtailment authority. It is not connected to `ControlDecision` in this
alpha.

## Building and actuator models

### Reference 1R1C model

The simulator and estimator shall retain a simple reference model:

```text
C dTi/dt = (To - Ti) / R + Qh + Qdisturbance
```

This model is useful for tests and conservative fallback estimates, but it cannot
separate room-air response from stored heat.

### Production 2R2C model

The preferred production grey-box model is:

```text
Ca dTa/dt = (Tm - Ta) / Ram + (To - Ta) / Rao + Qh + Qi + Qs
Cm dTm/dt = (Ta - Tm) / Ram
```

`Ta` is measured room temperature and `Tm` is latent thermal-mass temperature. The
model represents fast room response, slow storage, residual heat, cooling, and recovery.
Parameters are bounded by physical plausibility and accompanied by uncertainty and a
validated operating domain.

### Actuator separation

Virtual outdoor temperature is not heating power. A separate actuator model maps the
manipulated signal to delivered heat:

```text
Qh(t) = f(To(t - delay), Tvirtual(t - delay), actuator_parameters)
```

The model may include delay, local gain, heating-curve behaviour, minimum modulation,
saturation, cycling, and distribution-system afterheat. Optional compressor power,
energy, supply temperature, or operating status improves observability. In their
absence, authority remains conservative. Building heat loss and actuator response shall
never be collapsed into one empirical constant.

## Identification and confidence

Learning consumes structured Recorder history, not text logs. Candidate data is divided
into episodes and screened for freshness, time continuity, sensor plausibility,
actuator excitation, open-window signatures, solar/internal-gain disturbances, hot-water
events, and manual setpoint changes.

Confidence shall consider:

- independent informative episodes,
- parameter identifiability and uncertainty,
- residual bias and autocorrelation,
- multi-horizon out-of-sample prediction error,
- coverage of outdoor temperature and actuator ranges,
- drift and time since validation.

The estimator proposes model updates. A validator grants authority. Failed validation
retains the previous accepted model or reduces authority.

### Observation evidence boundary

Before parameter identification, the Recorder pipeline extracts only descriptive
temperature intervals. An interval requires progress of the indoor sensor's own
observation timestamp and uses elapsed wall-clock time; outdoor-only history rows do not
create false response samples. Intervals never cross an excluded observation, excessive
gap, target epoch, or episode boundary. A validated boundary sample may join the first
continued fragment after a batch or restart so that edge is counted exactly once.

This evidence may report observed rising, falling, or stable room temperature plus
coverage of optional command, power, and supply sensors. These names do not imply that
the heat pump caused the response. Target temperature remains user intent rather than an
actuator measurement. Latest-batch diagnostics are aggregate and explicitly grant no
parameter identifiability, confidence, or control authority. Cumulative estimator
evidence will require a separate versioned persistent format before it can contribute to
model validation.

## Simulation architecture

The simulator shall combine independently replaceable models for:

- 1R1C and 2R2C buildings,
- radiator, underfloor, and mixed heat distribution,
- heat-pump curve, delay, modulation, saturation, cycling, and COP,
- solar, internal gains, infiltration, window opening, and hot-water interruption,
- noise, quantization, stale/frozen sensors, missing data, restarts, and timestamp faults.

Scenarios use deterministic seeds and emit comfort, cost, energy, output movement,
prediction calibration, recovery, and fail-safe metrics.

## Persistence and adapters

Persisted control and model state shall have an explicit schema version, creation time,
input-source identity, validity domain, and checksum or validation step. Incompatible or
corrupt state is rejected safely.

The Home Assistant layer owns discovery, subscriptions, Recorder access, entity state,
service calls, and physical writes. The domain core never depends on entity IDs or
provider-specific price/weather attributes.
