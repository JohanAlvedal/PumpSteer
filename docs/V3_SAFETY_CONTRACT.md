# PumpSteer V3 Safety Contract

Status: Normative. An implementation that violates this contract is not releasable.

## Safety priorities

The fixed priority order is:

1. Prevent invalid or uncontrolled output.
2. Respect equipment and configured output limits.
3. Protect minimum comfort and recovery capability.
4. Maintain stable comfort control.
5. Optimize cost.

No price, forecast, learned parameter, restored state, or user economy preference may
reverse this order.

## Input invariants

1. Every reading carries an observation timestamp and source identity.
2. Critical readings are checked for presence, finiteness, plausible range, freshness,
   monotonic time, and plausible rate of change.
3. A frozen sensor is distinct from a merely stable temperature and requires
   source-aware detection plus corroborating evidence.
4. Missing or invalid price/weather data disables only the dependent optimization.
5. Missing, stale, invalid, or out-of-order indoor data disables adaptive planning.
6. Missing or invalid outdoor data invokes an explicitly configured safe-output policy;
   the previous manipulated output must not be silently retained.
7. Negative, zero, or excessive controller time steps are rejected or bounded and may
   not advance learning or ramps as normal data.

## Output invariants

1. Every commanded value is finite and within validated hardware bounds.
2. Step size and slew rate are enforced by the output supervisor independently of the
   comfort controller and planner.
3. Quantization occurs only after bounds and slew supervision.
4. A failed write is observable and retried only according to a bounded policy.
5. Loss of write acknowledgement reduces capability or enters fail-safe according to
   adapter policy.
6. Internal exceptions invoke an active safe-output attempt; setting an entity state to
   unavailable is not itself a safe physical action.
7. Restart recovery may not produce a larger output step than continuous operation would
   permit.
8. Shadow mode performs no physical write while producing otherwise identical decisions.

## Comfort invariants

1. Cost optimization is prohibited when critical comfort input is invalid.
2. Curtailment is prohibited when the conservative prediction interval threatens the
   comfort floor before adequate recovery is possible.
3. Curtailment releases predictively; it shall not rely only on detecting that the floor
   has already been crossed.
4. Increasing uncertainty reduces intervention depth or duration.
5. Recovery has priority over renewed curtailment until the recovery guard is cleared.
6. Setpoint changes take effect under a bounded transition policy and are not interpreted
   as changed building physics.
7. A conservative frost-protection policy applies independently of economy mode.

## Controller invariants

1. Controller state advances from explicit elapsed time, not assumed polling count.
2. Integrators implement anti-windup under output saturation and planner override.
3. Planner and comfort terms use the canonical sign convention.
4. The same influence is not counted in both the building model and a separate overlay.
5. Mode transitions are deterministic and emit reason codes.
6. Every decision records requested output, supervised output, active constraints,
   model version, authority level, and primary reason.

## Model and learning invariants

1. Learned models cannot control while `uninitialized` or `observing`.
2. Sample count alone cannot grant confidence.
3. Training and validation episodes are separated in time.
4. Model authority is limited to its validated outdoor-temperature, indoor-temperature,
   actuator, and time-horizon domain.
5. Extrapolation is explicit and reduces or removes planning authority.
6. Parameter estimates have physical bounds and uncertainty.
7. Building and actuator parameters are not updated together unless the available data
   makes them separately observable.
8. Episodes affected by likely window opening, strong unmodelled gains, sensor faults,
   hot-water interruption, or manual intervention are excluded or robustly downweighted.
9. Drift detection can demote a model to `degraded` or `stale` automatically.
10. A rejected candidate model cannot overwrite the last accepted model.
11. Persistence restores evidence, uncertainty, validity domain, and schema version; a
    bare parameter value is insufficient.

## Capability degradation

| Available trustworthy data | Maximum capability |
|---|---|
| Indoor + outdoor | Comfort-only control |
| Indoor + outdoor + weather | Forecast-aware comfort, no price shifting |
| Indoor + outdoor + price | Conservative price logic without weather claims |
| Indoor + outdoor + weather + price | Planning subject to model authority |
| Invalid indoor | No adaptive planning; defined fail-safe |
| Invalid outdoor | Defined adapter-specific safe-output policy |
| Invalid learned model | Comfort-only control with conservative defaults |

Capability recovery requires fresh valid observations and transition guards. A single
good sample does not immediately restore full authority.

## Required fault tests

Automated tests shall cover at least:

- indoor and outdoor sensor missing, stale, frozen, noisy, implausible, and recovering,
- price and weather missing independently and together,
- delayed, duplicated, and out-of-order observations,
- daylight-saving transitions and incomplete price days,
- Home Assistant restart during heating, preheat, curtailment, recovery, and fail-safe,
- corrupt and incompatible persisted state,
- write failure, missing acknowledgement, and output entity disappearance,
- controller exception and estimator exception,
- actuator saturation, excessive requested step, and irregular update intervals,
- open-window cooling, strong solar gain, internal-gain step, and hot-water interruption,
- heat pump at capacity during cold weather,
- model drift and operation outside the validated domain.

Property tests shall verify finite bounded output, deterministic replay, monotonic safety
authority under increasing uncertainty, and impossibility of price optimization when a
critical safety guard is active.

## Release evidence

Each release candidate shall include:

- a traceable matrix from every invariant to automated tests,
- simulator results for reference building and heat-system scenarios,
- multi-horizon model error and prediction-interval calibration,
- comfort violation and recovery metrics,
- fault-injection results,
- shadow-mode results from representative installations,
- active beta results within the declared operating envelope,
- documented residual risks and rollback procedure.

Any unresolved violation of an invariant blocks release. Safety defects discovered in a
release candidate require renewed beta-level validation for the affected behaviour.
