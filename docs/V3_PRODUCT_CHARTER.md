# PumpSteer V3 Product Charter

Status: Binding design charter for PumpSteer 3.0 development.

## Product promise

PumpSteer V3 shall be a free, local-first Home Assistant heating controller that
provides a credible software alternative to commercial outdoor-temperature
compensators such as Ngenic. It shall improve comfort and shift heating away from
costly periods by manipulating the outdoor-temperature signal presented to the heat
pump, without requiring the user to tune control parameters.

The normal installation shall require only:

1. An indoor temperature sensor.
2. A real outdoor temperature sensor.
3. A desired indoor temperature.

Weather and electricity-price sources shall be discovered automatically when
possible. Their absence shall reduce optimization capability, not disable comfort
control. If discovery is ambiguous, PumpSteer shall ask the user rather than silently
select an uncertain source.

## Product principles

- Comfort and equipment safety always take precedence over cost.
- All control and learning run locally in Home Assistant.
- Normal users do not tune PI gains, inertia, ramps, preheat duration, brake depth,
  thermal time constants, or price percentiles.
- Economy preference is one `saving_level` from 0 to 5. Level 0 disables price
  classification; higher levels select fixed internal cheap/expensive percentiles.
  This preference can never increase model or physical-control authority.
- Adaptation is bounded, confidence-aware, reversible, and explainable.
- Every decision exposes a stable reason code and the constraints that affected it.
- Missing optional data produces a defined capability reduction.
- Missing critical data produces an active, defined fail-safe action.
- The same deterministic decision function is used in simulation, shadow mode, and
  active control.
- Advanced diagnostics may expose expert detail, but expert settings must not be
  required for correct normal operation.

## Scope for 3.0

- A `climate`-centred Home Assistant experience.
- Comfort-only control using indoor and outdoor temperature.
- Safe generation and delivery of virtual outdoor temperature.
- Automatic discovery of compatible weather and electricity-price sources.
- Normalized, timestamped weather and price timelines.
- Recorder-backed thermal learning with explicit confidence and validity domains.
- A grey-box building model and a separate heat-system actuator model.
- Predictive, bounded preheating and curtailment.
- Shadow mode, diagnostics, model persistence, and safe restart behaviour.
- Support for common radiator, underfloor-heating, and mixed-system dynamics.
- Migration documentation from V2. V3 is a breaking release; V2 entity and option
  compatibility is not a design constraint.

## Non-goals

- Controlling domestic hot water, cooling, ventilation, or individual room valves in
  3.0.
- Claiming measured heat energy when no suitable energy measurement exists.
- Unbounded reinforcement learning, opaque neural-network control, or decisions that
  cannot be explained from their inputs.
- Guaranteeing compatibility with every proprietary heat-pump interface.
- Replacing physical interface hardware required to inject an outdoor-temperature
  signal.
- Optimizing cost before the comfort and fail-safe controller is validated.
- Treating a human wind-chill formula as a building heat-loss model.

## User-visible behaviour

PumpSteer shall present a small set of meaningful controls: target temperature,
enable/disable, and at most a simple comfort/economy preference if testing shows it is
needed. Learning state, confidence, current mode, reason, input freshness, predicted
comfort margin, and output limitations shall be visible as diagnostics rather than
required configuration.

Learning shall progress through explicit authority levels:

- `uninitialized`: no learned model authority.
- `observing`: collection and prediction only.
- `provisional`: short, conservative interventions.
- `validated`: bounded planning within the model's validated domain.
- `degraded`: authority reduced after drift or data-quality failure.
- `stale`: learned parameters are not trusted for current conditions.

## Release gates

PumpSteer 3.0 shall not be declared stable until all of the following are met:

- Unit, property, scenario, restart, and fault-injection tests cover the safety
  contract.
- Comfort-only operation works without price or weather data.
- A missing, stale, frozen, invalid, or out-of-order critical sensor has a tested
  response.
- Internal exceptions cannot silently leave an unsafe manipulated output active.
- Output bounds, slew limits, and finite-value checks are enforced independently of
  the planner.
- Model confidence is based on prediction quality, excitation, data coverage, and
  uncertainty, not sample count alone.
- Learning cannot gain authority from contaminated or unobservable episodes.
- Shadow predictions have been validated across light radiator, heavy radiator,
  underfloor-heating, and mixed-system scenarios.
- Active beta testing demonstrates bounded comfort deviation and safe recovery across
  representative heating-season conditions.
- Persistence is versioned and restart behaviour is deterministic.
- Migration, installation, diagnostics, rollback, and troubleshooting documentation
  is complete.
- Release-candidate development is limited to defect correction; unresolved safety or
  architecture issues return the release to beta.

No finite test programme proves perfection for every building. Stable release means
that the documented operating envelope, failure behaviour, and residual risks are
measured, reviewed, and acceptable.

## Development order

1. Freeze the V2 behaviour as a reference and define V3 contracts.
2. Build a deterministic simulator and pure comfort-only controller.
3. Implement output supervision, fail-safe behaviour, and fault injection.
4. Add the Home Assistant adapters and run the controller in shadow mode.
5. Add thermal and actuator identification without granting control authority.
6. Validate multi-horizon predictions and confidence calibration.
7. Permit conservative, short interventions within the validated domain.
8. Add price and weather planning.
9. Expand beta testing, then complete release gates before 3.0 stable.
