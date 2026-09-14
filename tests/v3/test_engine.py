"""Tests for the pure V3 Observation-to-Decision engine."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3 import (
    ComfortPolicy,
    ControlState,
    Observation,
    ReasonCode,
    SafetyPolicy,
    SensorReading,
    Unit,
)
from custom_components.pumpsteer.v3.control.engine import (
    ControlEngine,
    ControlEngineConfig,
    EngineState,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def make_observation(
    *,
    now: datetime = NOW,
    indoor_observed_at: datetime | None = None,
    outdoor_observed_at: datetime | None = None,
    with_optional_data: bool = False,
    indoor: float = 20.0,
    outdoor: float = -5.0,
) -> Observation:
    indoor_at = indoor_observed_at or now
    outdoor_at = outdoor_observed_at or now
    price = (
        SensorReading(1.25, now, Unit.SEK_PER_KWH, "price.test")
        if with_optional_data
        else None
    )
    forecast = (
        (SensorReading(-6.0, now, Unit.CELSIUS, "weather.test"),)
        if with_optional_data
        else ()
    )
    return Observation(
        captured_at=now,
        indoor=SensorReading(indoor, indoor_at, Unit.CELSIUS, "indoor.test"),
        outdoor=SensorReading(outdoor, outdoor_at, Unit.CELSIUS, "outdoor.test"),
        electricity_price=price,
        forecast_outdoor=forecast,
    )


def run(
    engine: ControlEngine,
    *,
    observation: Observation | None = None,
    state: EngineState = EngineState(),
    now: datetime = NOW,
    dt: timedelta = timedelta(minutes=1),
    shadow: bool = False,
):
    return engine.step(
        observation=observation
        if observation is not None
        else make_observation(now=now),
        comfort_policy=ComfortPolicy(),
        safety_policy=SafetyPolicy(),
        state=state,
        now_utc=now,
        dt=dt,
        shadow=shadow,
    )


def test_valid_observation_runs_comfort_controller_and_supervisor() -> None:
    result = run(ControlEngine())

    assert result.requested_decision is not None
    assert result.supervised_output.decision.state is ControlState.COMFORT
    assert result.supervised_output.value <= -5.0
    assert (
        ReasonCode.COMFORT_BELOW_TARGET
        in result.supervised_output.decision.reason_codes
    )
    assert result.apply_physical


def test_optional_price_and_weather_do_not_change_comfort_only_result() -> None:
    without_optional = run(ControlEngine(), observation=make_observation())
    with_optional = run(
        ControlEngine(), observation=make_observation(with_optional_data=True)
    )

    assert without_optional.requested_decision == with_optional.requested_decision
    assert without_optional.supervised_output == with_optional.supervised_output


def test_above_target_requests_comfort_curtailment_with_explainable_reason() -> None:
    result = run(ControlEngine(), observation=make_observation(indoor=22.0))

    assert result.requested_decision is not None
    assert result.requested_decision.heating_request == 0.0
    assert result.requested_decision.curtailment > 0.0
    assert result.requested_decision.virtual_temperature > -5.0
    assert ReasonCode.COMFORT_ABOVE_TARGET in result.requested_decision.reason_codes


def test_first_active_command_uses_outdoor_as_slew_limited_startup_baseline() -> None:
    result = run(ControlEngine(), observation=make_observation(indoor=15.0))

    assert result.requested_decision is not None
    assert result.requested_decision.heating_request > 2.0
    assert result.supervised_output.value == pytest.approx(-6.0)
    assert ReasonCode.OUTPUT_RATE_LIMITED in (
        result.supervised_output.decision.reason_codes
    )


def test_summer_passthrough_has_hysteresis_and_clears_integral() -> None:
    engine = ControlEngine(
        config=ControlEngineConfig(summer_threshold=18.0, summer_hysteresis=1.0)
    )
    entered = run(engine, observation=make_observation(outdoor=18.0))
    assert entered.supervised_output.decision.state is ControlState.SUMMER_PASSTHROUGH
    assert entered.supervised_output.fallback_active is True
    assert entered.supervised_output.value == 18.0
    assert entered.next_state.summer_passthrough_active

    within_hysteresis_at = NOW + timedelta(minutes=1)
    held = run(
        engine,
        observation=make_observation(now=within_hysteresis_at, outdoor=17.5),
        state=entered.next_state,
        now=within_hysteresis_at,
    )
    assert held.supervised_output.decision.state is ControlState.SUMMER_PASSTHROUGH
    assert held.supervised_output.value == 17.5
    assert held.next_state.comfort.integral == 0.0

    exit_at = within_hysteresis_at + timedelta(minutes=1)
    exited = run(
        engine,
        observation=make_observation(now=exit_at, outdoor=17.0),
        state=held.next_state,
        now=exit_at,
    )
    assert exited.supervised_output.decision.state is ControlState.COMFORT
    assert not exited.next_state.summer_passthrough_active


def test_recovery_requires_three_consecutive_valid_observations() -> None:
    engine = ControlEngine(config=ControlEngineConfig(recovery_valid_observations=3))
    stale = NOW - timedelta(minutes=11)
    failed = run(
        engine,
        observation=make_observation(indoor_observed_at=stale),
    )
    assert failed.next_state.recovery_required

    state = failed.next_state
    for cycle in (1, 2):
        now = NOW + timedelta(minutes=cycle)
        recovering = run(
            engine,
            observation=make_observation(now=now),
            state=state,
            now=now,
        )
        assert recovering.supervised_output.decision.state is ControlState.RECOVERY
        assert recovering.supervised_output.fallback_active is True
        assert recovering.supervised_output.value == -5.0
        assert ReasonCode.RECOVERY_VALIDATION_PENDING in (
            recovering.supervised_output.decision.reason_codes
        )
        state = recovering.next_state

    recovered_at = NOW + timedelta(minutes=3)
    recovered = run(
        engine,
        observation=make_observation(now=recovered_at),
        state=state,
        now=recovered_at,
    )
    assert recovered.supervised_output.decision.state is ControlState.COMFORT
    assert not recovered.next_state.recovery_required


def test_invalid_observation_resets_recovery_streak() -> None:
    engine = ControlEngine()
    stale = NOW - timedelta(minutes=11)
    failed = run(
        engine,
        observation=make_observation(indoor_observed_at=stale),
    )
    first_valid_at = NOW + timedelta(minutes=1)
    first_valid = run(
        engine,
        observation=make_observation(now=first_valid_at),
        state=failed.next_state,
        now=first_valid_at,
    )
    assert first_valid.next_state.consecutive_valid_observations == 1

    failed_again_at = NOW + timedelta(minutes=2)
    stale_again = failed_again_at - timedelta(minutes=11)
    failed_again = run(
        engine,
        observation=make_observation(
            now=failed_again_at,
            indoor_observed_at=stale_again,
        ),
        state=first_valid.next_state,
        now=failed_again_at,
    )
    assert failed_again.next_state.recovery_required
    assert failed_again.next_state.consecutive_valid_observations == 0


def test_recovery_does_not_count_repeated_source_timestamps_twice() -> None:
    engine = ControlEngine()
    stale = NOW - timedelta(minutes=11)
    failed = run(
        engine,
        observation=make_observation(indoor_observed_at=stale),
    )
    first_valid_at = NOW + timedelta(minutes=1)
    first_valid = run(
        engine,
        observation=make_observation(now=first_valid_at),
        state=failed.next_state,
        now=first_valid_at,
    )

    next_cycle_at = NOW + timedelta(minutes=2)
    repeated = run(
        engine,
        observation=make_observation(
            now=next_cycle_at,
            indoor_observed_at=first_valid_at,
            outdoor_observed_at=first_valid_at,
        ),
        state=first_valid.next_state,
        now=next_cycle_at,
    )

    assert repeated.supervised_output.decision.state is ControlState.RECOVERY
    assert repeated.next_state.consecutive_valid_observations == 1


@pytest.mark.parametrize(
    ("indoor", "outdoor", "specific_reason"),
    [
        (4.9, -5.0, ReasonCode.INDOOR_SENSOR_INVALID),
        (35.1, -5.0, ReasonCode.INDOOR_SENSOR_INVALID),
        (20.0, -50.1, ReasonCode.OUTDOOR_SENSOR_INVALID),
        (20.0, 50.1, ReasonCode.OUTDOOR_SENSOR_INVALID),
    ],
)
def test_implausible_critical_temperature_enters_failsafe(
    indoor: float,
    outdoor: float,
    specific_reason: ReasonCode,
) -> None:
    result = run(
        ControlEngine(),
        observation=make_observation(indoor=indoor, outdoor=outdoor),
    )

    assert result.requested_decision is None
    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert specific_reason in result.input_reasons
    assert ReasonCode.SENSOR_OUT_OF_RANGE in result.input_reasons


def test_stale_indoor_enters_failsafe_and_passes_through_outdoor() -> None:
    stale = NOW - timedelta(minutes=11)
    result = run(
        ControlEngine(), observation=make_observation(indoor_observed_at=stale)
    )

    assert result.requested_decision is None
    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == -5.0
    assert result.supervised_output.fallback_active
    assert ReasonCode.STALE_SENSOR in result.supervised_output.decision.reason_codes
    assert (
        ReasonCode.INDOOR_SENSOR_INVALID
        in result.supervised_output.decision.reason_codes
    )


def test_stale_outdoor_has_defined_failsafe_passthrough() -> None:
    stale = NOW - timedelta(minutes=11)
    result = run(
        ControlEngine(), observation=make_observation(outdoor_observed_at=stale)
    )

    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == -5.0
    assert (
        ReasonCode.OUTDOOR_SENSOR_INVALID
        in result.supervised_output.decision.reason_codes
    )


def test_missing_observation_uses_supervisor_safe_fallback() -> None:
    result = ControlEngine().step(
        observation=None,
        comfort_policy=ComfortPolicy(),
        safety_policy=SafetyPolicy(),
        state=EngineState(),
        now_utc=NOW,
        dt=timedelta(minutes=1),
    )

    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == 10.0
    assert (
        ReasonCode.CRITICAL_SENSOR_INVALID
        in result.supervised_output.decision.reason_codes
    )


def test_missing_indoor_can_use_separately_validated_outdoor_passthrough() -> None:
    result = ControlEngine().step(
        observation=None,
        comfort_policy=ComfortPolicy(),
        safety_policy=SafetyPolicy(),
        state=EngineState(),
        now_utc=NOW,
        dt=timedelta(minutes=1),
        fallback_outdoor_temperature=-7.0,
    )

    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == -7.0


def test_shadow_produces_same_value_without_physical_application() -> None:
    active = run(ControlEngine())
    shadow = run(ControlEngine(), shadow=True)

    assert shadow.supervised_output.value == active.supervised_output.value
    assert not shadow.apply_physical
    assert ReasonCode.SHADOW_MODE in shadow.supervised_output.decision.reason_codes


def test_restart_gap_is_bounded_by_comfort_controller_and_output_step() -> None:
    engine = ControlEngine()
    first = run(engine)
    later = NOW + timedelta(hours=2)
    second = run(
        engine,
        observation=make_observation(now=later),
        state=first.next_state,
        now=later,
        dt=timedelta(hours=2),
    )

    assert second.comfort_result is not None
    assert second.comfort_result.dt_bounded
    assert abs(second.supervised_output.value - first.supervised_output.value) <= 2.0


def test_failsafe_clears_integral_for_deterministic_recovery() -> None:
    stale = NOW - timedelta(minutes=11)
    failed = run(
        ControlEngine(), observation=make_observation(indoor_observed_at=stale)
    )

    assert failed.next_state.comfort.integral == 0.0
    assert failed.next_state.comfort.last_step_at == NOW


def test_explicit_dt_must_match_engine_state() -> None:
    first = run(ControlEngine())
    later = NOW + timedelta(minutes=2)

    with pytest.raises(ValueError, match="dt must match"):
        run(
            ControlEngine(),
            observation=make_observation(now=later),
            state=first.next_state,
            now=later,
            dt=timedelta(minutes=1),
        )


def test_out_of_order_critical_timestamp_enters_failsafe() -> None:
    engine = ControlEngine()
    first = run(engine)
    later = NOW + timedelta(minutes=1)
    regressed = make_observation(
        now=later,
        indoor_observed_at=NOW - timedelta(seconds=1),
        outdoor_observed_at=later,
    )

    result = run(
        engine,
        observation=regressed,
        state=first.next_state,
        now=later,
        dt=timedelta(minutes=1),
    )

    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert ReasonCode.INDOOR_SENSOR_INVALID in result.input_reasons
    assert ReasonCode.SENSOR_TIME_REGRESSION in result.input_reasons
    assert result.next_state.last_indoor_observed_at == NOW


def test_explicit_internal_failsafe_is_supervised_and_shadow_safe() -> None:
    result = ControlEngine().fail_safe(
        safety_policy=SafetyPolicy(),
        state=EngineState(),
        now_utc=NOW,
        shadow=True,
        fallback_outdoor_temperature=-9.0,
    )

    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == -9.0
    assert not result.apply_physical
    assert result.input_reasons == (ReasonCode.INTERNAL_FAILSAFE,)
