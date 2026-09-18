"""Pure Observation-to-Decision engine for PumpSteer V3."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from ..enums import ControlState, ReasonCode
from ..models import ComfortPolicy, ControlDecision, Observation, SafetyPolicy
from ..validation import aware_datetime, finite_float
from .comfort_controller import (
    ComfortController,
    ComfortControllerResult,
    ComfortControllerState,
)
from .preheat import PreheatContext, PreheatPlan, plan_automatic_preheat
from .supervisor import (
    SupervisedOutput,
    SupervisorPolicy,
    supervise_output,
)


@dataclass(frozen=True, slots=True)
class ControlEngineConfig:
    """Conservative state-machine policy for the pure control engine."""

    summer_threshold: float = 18.0
    summer_hysteresis: float = 1.0
    recovery_valid_observations: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "summer_threshold",
            finite_float(self.summer_threshold, "summer_threshold"),
        )
        object.__setattr__(
            self,
            "summer_hysteresis",
            finite_float(self.summer_hysteresis, "summer_hysteresis"),
        )
        if self.summer_hysteresis < 0:
            raise ValueError("summer_hysteresis must be non-negative")
        if isinstance(self.recovery_valid_observations, bool) or not isinstance(
            self.recovery_valid_observations, int
        ):
            raise TypeError("recovery_valid_observations must be an integer")
        if self.recovery_valid_observations < 2:
            raise ValueError("recovery_valid_observations must be at least 2")


@dataclass(frozen=True, slots=True)
class EngineState:
    """Immutable state required by the next engine cycle."""

    comfort: ComfortControllerState = ComfortControllerState()
    previous_output: SupervisedOutput | None = None
    last_indoor_observed_at: datetime | None = None
    last_outdoor_observed_at: datetime | None = None
    summer_passthrough_active: bool = False
    recovery_required: bool = False
    consecutive_valid_observations: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "last_indoor_observed_at",
            "last_outdoor_observed_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_utc(value)
        if not isinstance(self.summer_passthrough_active, bool):
            raise TypeError("summer_passthrough_active must be a bool")
        if not isinstance(self.recovery_required, bool):
            raise TypeError("recovery_required must be a bool")
        if isinstance(self.consecutive_valid_observations, bool) or not isinstance(
            self.consecutive_valid_observations, int
        ):
            raise TypeError("consecutive_valid_observations must be an integer")
        if self.consecutive_valid_observations < 0:
            raise ValueError("consecutive_valid_observations must be non-negative")
        if not self.recovery_required and self.consecutive_valid_observations:
            raise ValueError(
                "valid-observation streak requires an active recovery guard"
            )


@dataclass(frozen=True, slots=True)
class EngineResult:
    """Requested and supervised results from one complete engine cycle."""

    requested_decision: ControlDecision | None
    supervised_output: SupervisedOutput
    comfort_result: ComfortControllerResult | None
    input_reasons: tuple[ReasonCode, ...]
    next_state: EngineState
    preheat_plan: PreheatPlan | None = None

    @property
    def apply_physical(self) -> bool:
        """Return whether the adapter may apply the supervised output."""
        return self.supervised_output.apply_physical


class ControlEngine:
    """Validate inputs, run comfort control, and supervise final output."""

    def __init__(
        self,
        *,
        comfort_controller: ComfortController | None = None,
        supervisor_policy: SupervisorPolicy | None = None,
        config: ControlEngineConfig | None = None,
    ) -> None:
        self._comfort = comfort_controller or ComfortController()
        self._supervisor_policy = supervisor_policy or SupervisorPolicy()
        self._config = config or ControlEngineConfig()

    def step(
        self,
        *,
        observation: Observation | None,
        comfort_policy: ComfortPolicy,
        safety_policy: SafetyPolicy,
        state: EngineState,
        now_utc: datetime,
        dt: timedelta,
        shadow: bool = False,
        override_active: bool = False,
        fallback_outdoor_temperature: float | None = None,
        saving_level: object = 0,
        preheat_context: PreheatContext | None = None,
    ) -> EngineResult:
        """Run one deterministic control cycle.

        Price and weather remain optional capabilities. Automatic preheat is only
        considered when a validated future price opportunity and an authorized
        thermal prediction are supplied. Invalid critical inputs always take the
        same output-supervisor fail-safe path.
        """
        now = _require_utc(now_utc)
        if not isinstance(comfort_policy, ComfortPolicy):
            raise TypeError("comfort_policy must be a ComfortPolicy")
        if not isinstance(safety_policy, SafetyPolicy):
            raise TypeError("safety_policy must be a SafetyPolicy")
        if not isinstance(state, EngineState):
            raise TypeError("state must be an EngineState")
        if not isinstance(dt, timedelta):
            raise TypeError("dt must be a timedelta")
        if dt <= timedelta(0):
            raise ValueError("dt must be positive")

        reasons, fallback_outdoor = _validate_critical_inputs(
            observation, now, safety_policy, state
        )
        if fallback_outdoor is None and observation is None:
            fallback_outdoor = fallback_outdoor_temperature
        if reasons:
            supervised = supervise_output(
                None,
                safety=safety_policy,
                policy=self._supervisor_policy,
                now=now,
                previous=state.previous_output,
                shadow=shadow,
                critical_input_valid=False,
                internal_failure=False,
                fallback_outdoor_temperature=fallback_outdoor,
            )
            supervised = _with_reasons(supervised, reasons)
            # A fail-safe transition clears accumulated heat demand. Recording
            # the transition instant allows deterministic recovery on next cycle.
            next_state = EngineState(
                comfort=ComfortControllerState(integral=0.0, last_step_at=now),
                previous_output=supervised,
                last_indoor_observed_at=state.last_indoor_observed_at,
                last_outdoor_observed_at=state.last_outdoor_observed_at,
                summer_passthrough_active=state.summer_passthrough_active,
                recovery_required=True,
                consecutive_valid_observations=0,
            )
            return EngineResult(
                requested_decision=None,
                supervised_output=supervised,
                comfort_result=None,
                input_reasons=reasons,
                next_state=next_state,
                preheat_plan=None,
            )

        assert observation is not None
        recovery_required = state.recovery_required
        valid_observations = state.consecutive_valid_observations
        if recovery_required:
            # Critical inputs have already passed range, freshness, and timestamp
            # validation for this cycle. Count consecutive valid control cycles
            # rather than requiring a new sensor timestamp on every cycle; stable
            # sensors must be allowed to recover without manufacturing state changes.
            valid_observations += 1
            if valid_observations >= self._config.recovery_valid_observations:
                recovery_required = False
                valid_observations = 0

        summer_active = _summer_passthrough_active(
            outdoor_temperature=observation.outdoor.value,
            was_active=state.summer_passthrough_active,
            config=self._config,
        )
        if summer_active:
            return _passthrough_result(
                observation=observation,
                safety_policy=safety_policy,
                supervisor_policy=self._supervisor_policy,
                now=now,
                shadow=shadow,
                control_state=ControlState.SUMMER_PASSTHROUGH,
                reason=ReasonCode.SUMMER_PASSTHROUGH,
                summer_active=True,
                recovery_required=recovery_required,
                valid_observations=valid_observations,
            )

        if recovery_required:
            return _passthrough_result(
                observation=observation,
                safety_policy=safety_policy,
                supervisor_policy=self._supervisor_policy,
                now=now,
                shadow=shadow,
                control_state=ControlState.RECOVERY,
                reason=ReasonCode.RECOVERY_VALIDATION_PENDING,
                summer_active=False,
                recovery_required=True,
                valid_observations=valid_observations,
            )

        preheat_plan = plan_automatic_preheat(
            observation=observation,
            comfort_policy=comfort_policy,
            saving_level=saving_level,
            context=preheat_context,
        )
        effective_policy = comfort_policy
        planner_override = bool(override_active)
        requested_state = ControlState.COMFORT
        if preheat_plan.active:
            effective_policy = replace(
                comfort_policy,
                target_temperature=preheat_plan.effective_target_temperature,
            )
            planner_override = True
            requested_state = ControlState.PREHEAT

        comfort_result = self._comfort.step(
            observation=observation,
            policy=effective_policy,
            safety_policy=safety_policy,
            state=state.comfort,
            now_utc=now,
            dt=dt,
            override_active=planner_override,
        )
        if preheat_plan.active:
            decision_reasons = (
                ReasonCode.PREDICTED_COMFORT_RISK,
                ReasonCode.PRICE_SHIFT_BENEFICIAL,
            )
        else:
            if comfort_result.effective_error > 0.0:
                primary_reason = ReasonCode.COMFORT_BELOW_TARGET
            elif comfort_result.effective_error < 0.0:
                primary_reason = ReasonCode.COMFORT_ABOVE_TARGET
            else:
                primary_reason = ReasonCode.COMFORT_WITHIN_BAND
            decision_reasons = (primary_reason,)
        requested = ControlDecision.create(
            decided_at=now,
            state=requested_state,
            outdoor_temperature=observation.outdoor.value,
            heating_request=comfort_result.heating_request,
            curtailment=comfort_result.curtailment,
            reason_codes=decision_reasons,
        )
        previous_output = state.previous_output
        if previous_output is None:
            previous_output = _initial_passthrough_baseline(
                observation=observation,
                safety_policy=safety_policy,
                supervisor_policy=self._supervisor_policy,
                now=now - dt,
                shadow=shadow,
            )
        supervised = supervise_output(
            requested,
            safety=safety_policy,
            policy=self._supervisor_policy,
            now=now,
            previous=previous_output,
            shadow=shadow,
        )
        next_state = EngineState(
            comfort=comfort_result.next_state,
            previous_output=supervised,
            last_indoor_observed_at=observation.indoor.observed_at,
            last_outdoor_observed_at=observation.outdoor.observed_at,
            summer_passthrough_active=False,
            recovery_required=False,
            consecutive_valid_observations=0,
        )
        return EngineResult(
            requested_decision=requested,
            supervised_output=supervised,
            comfort_result=comfort_result,
            input_reasons=(),
            next_state=next_state,
            preheat_plan=preheat_plan,
        )

    def fail_safe(
        self,
        *,
        safety_policy: SafetyPolicy,
        state: EngineState,
        now_utc: datetime,
        shadow: bool,
        fallback_outdoor_temperature: float | None = None,
    ) -> EngineResult:
        """Create an explicit supervised result after an internal failure."""
        now = _require_utc(now_utc)
        supervised = supervise_output(
            None,
            safety=safety_policy,
            policy=self._supervisor_policy,
            now=now,
            previous=state.previous_output,
            shadow=shadow,
            internal_failure=True,
            fallback_outdoor_temperature=fallback_outdoor_temperature,
        )
        next_state = EngineState(
            comfort=ComfortControllerState(integral=0.0, last_step_at=now),
            previous_output=supervised,
            last_indoor_observed_at=state.last_indoor_observed_at,
            last_outdoor_observed_at=state.last_outdoor_observed_at,
            summer_passthrough_active=state.summer_passthrough_active,
            recovery_required=True,
            consecutive_valid_observations=0,
        )
        return EngineResult(
            requested_decision=None,
            supervised_output=supervised,
            comfort_result=None,
            input_reasons=(ReasonCode.INTERNAL_FAILSAFE,),
            next_state=next_state,
            preheat_plan=None,
        )


def _validate_critical_inputs(
    observation: Observation | None,
    now: datetime,
    safety: SafetyPolicy,
    state: EngineState,
) -> tuple[tuple[ReasonCode, ...], float | None]:
    if observation is None:
        return (ReasonCode.CRITICAL_SENSOR_INVALID,), None
    outdoor_plausible = (
        safety.minimum_outdoor_temperature
        <= observation.outdoor.value
        <= safety.maximum_outdoor_temperature
    )
    fallback_outdoor = observation.outdoor.value if outdoor_plausible else None
    if observation.captured_at != now:
        return (ReasonCode.CRITICAL_SENSOR_INVALID,), fallback_outdoor

    reasons: list[ReasonCode] = []
    for reading, previous_timestamp, invalid_reason, minimum, maximum in (
        (
            observation.indoor,
            state.last_indoor_observed_at,
            ReasonCode.INDOOR_SENSOR_INVALID,
            safety.minimum_indoor_temperature,
            safety.maximum_indoor_temperature,
        ),
        (
            observation.outdoor,
            state.last_outdoor_observed_at,
            ReasonCode.OUTDOOR_SENSOR_INVALID,
            safety.minimum_outdoor_temperature,
            safety.maximum_outdoor_temperature,
        ),
    ):
        if not minimum <= reading.value <= maximum:
            reasons.extend((invalid_reason, ReasonCode.SENSOR_OUT_OF_RANGE))
        try:
            age = reading.age_at(now)
        except ValueError:
            reasons.append(invalid_reason)
            continue
        if age > safety.maximum_sensor_age:
            reasons.extend((invalid_reason, ReasonCode.STALE_SENSOR))
        if previous_timestamp is not None and reading.observed_at < previous_timestamp:
            reasons.extend((invalid_reason, ReasonCode.SENSOR_TIME_REGRESSION))

    return tuple(dict.fromkeys(reasons)), fallback_outdoor


def _summer_passthrough_active(
    *,
    outdoor_temperature: float,
    was_active: bool,
    config: ControlEngineConfig,
) -> bool:
    if was_active:
        return outdoor_temperature > (
            config.summer_threshold - config.summer_hysteresis
        )
    return outdoor_temperature >= config.summer_threshold


def _passthrough_result(
    *,
    observation: Observation,
    safety_policy: SafetyPolicy,
    supervisor_policy: SupervisorPolicy,
    now: datetime,
    shadow: bool,
    control_state: ControlState,
    reason: ReasonCode,
    summer_active: bool,
    recovery_required: bool,
    valid_observations: int,
) -> EngineResult:
    requested = ControlDecision.create(
        decided_at=now,
        state=control_state,
        outdoor_temperature=observation.outdoor.value,
        reason_codes=(reason,),
    )
    # Passthrough is a neutral safety action. It must not be delayed by a
    # previously manipulated output's slew limit.
    supervised = supervise_output(
        requested,
        safety=safety_policy,
        policy=supervisor_policy,
        now=now,
        previous=None,
        shadow=shadow,
    )
    # A semantic passthrough must also tell physical adapters to release their
    # manipulated path. Merely commanding a value equal to the outdoor sensor
    # would leave a relay or generic service path active during recovery/summer.
    supervised = replace(supervised, fallback_active=True)
    next_state = EngineState(
        comfort=ComfortControllerState(integral=0.0, last_step_at=now),
        previous_output=supervised,
        last_indoor_observed_at=observation.indoor.observed_at,
        last_outdoor_observed_at=observation.outdoor.observed_at,
        summer_passthrough_active=summer_active,
        recovery_required=recovery_required,
        consecutive_valid_observations=valid_observations,
    )
    return EngineResult(
        requested_decision=requested,
        supervised_output=supervised,
        comfort_result=None,
        input_reasons=(),
        next_state=next_state,
        preheat_plan=None,
    )


def _initial_passthrough_baseline(
    *,
    observation: Observation,
    safety_policy: SafetyPolicy,
    supervisor_policy: SupervisorPolicy,
    now: datetime,
    shadow: bool,
) -> SupervisedOutput:
    """Create a neutral first-cycle baseline so restart cannot bypass slew limits."""
    neutral = ControlDecision.create(
        decided_at=now,
        state=ControlState.PASSTHROUGH,
        outdoor_temperature=observation.outdoor.value,
        reason_codes=(ReasonCode.STARTUP_BASELINE,),
    )
    return supervise_output(
        neutral,
        safety=safety_policy,
        policy=supervisor_policy,
        now=now,
        previous=None,
        shadow=shadow,
    )


def _with_reasons(
    output: SupervisedOutput, extra_reasons: tuple[ReasonCode, ...]
) -> SupervisedOutput:
    reasons = tuple(dict.fromkeys((*output.decision.reason_codes, *extra_reasons)))
    decision = ControlDecision.create(
        decided_at=output.decision.decided_at,
        state=output.decision.state,
        outdoor_temperature=output.decision.outdoor_temperature,
        heating_request=output.decision.heating_request,
        curtailment=output.decision.curtailment,
        reason_codes=reasons,
    )
    return SupervisedOutput(
        decision=decision,
        apply_physical=output.apply_physical,
        constraints=output.constraints,
        fallback_active=output.fallback_active,
    )


def _require_utc(value: datetime) -> datetime:
    result = aware_datetime(value, "now_utc")
    if result.utcoffset() != timedelta(0):
        raise ValueError("now_utc must use UTC")
    return result
