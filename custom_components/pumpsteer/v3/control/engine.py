"""Pure Observation-to-Decision engine for PumpSteer V3."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from ..enums import ControlState, ReasonCode
from ..models import ComfortPolicy, ControlDecision, Observation, SafetyPolicy
from ..validation import aware_datetime
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
class EngineState:
    """Immutable state required by the next engine cycle."""

    comfort: ComfortControllerState = ComfortControllerState()
    previous_output: SupervisedOutput | None = None
    last_indoor_observed_at: datetime | None = None
    last_outdoor_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "last_indoor_observed_at",
            "last_outdoor_observed_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_utc(value)


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
    ) -> None:
        self._comfort = comfort_controller or ComfortController()
        self._supervisor_policy = supervisor_policy or SupervisorPolicy()

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
        if fallback_outdoor is None:
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
            primary_reason = (
                ReasonCode.COMFORT_BELOW_TARGET
                if comfort_result.effective_error > 0.0
                else ReasonCode.COMFORT_WITHIN_BAND
            )
            decision_reasons = (primary_reason,)
        requested = ControlDecision.create(
            decided_at=now,
            state=requested_state,
            outdoor_temperature=observation.outdoor.value,
            heating_request=comfort_result.heating_request,
            reason_codes=decision_reasons,
        )
        supervised = supervise_output(
            requested,
            safety=safety_policy,
            policy=self._supervisor_policy,
            now=now,
            previous=state.previous_output,
            shadow=shadow,
        )
        next_state = EngineState(
            comfort=comfort_result.next_state,
            previous_output=supervised,
            last_indoor_observed_at=observation.indoor.observed_at,
            last_outdoor_observed_at=observation.outdoor.observed_at,
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
    if observation.captured_at != now:
        return (ReasonCode.CRITICAL_SENSOR_INVALID,), observation.outdoor.value

    reasons: list[ReasonCode] = []
    for reading, previous_timestamp, invalid_reason in (
        (
            observation.indoor,
            state.last_indoor_observed_at,
            ReasonCode.INDOOR_SENSOR_INVALID,
        ),
        (
            observation.outdoor,
            state.last_outdoor_observed_at,
            ReasonCode.OUTDOOR_SENSOR_INVALID,
        ),
    ):
        try:
            age = reading.age_at(now)
        except ValueError:
            reasons.append(invalid_reason)
            continue
        if age > safety.maximum_sensor_age:
            reasons.extend((invalid_reason, ReasonCode.STALE_SENSOR))
        if previous_timestamp is not None and reading.observed_at < previous_timestamp:
            reasons.extend((invalid_reason, ReasonCode.SENSOR_TIME_REGRESSION))

    return tuple(dict.fromkeys(reasons)), observation.outdoor.value


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
