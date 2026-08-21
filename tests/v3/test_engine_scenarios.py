"""End-to-end safety scenarios for the pure PumpSteer V3 control engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.pumpsteer.v3.control.engine import (
    ControlEngine,
    EngineState,
)
from custom_components.pumpsteer.v3.enums import ControlState, ReasonCode, Unit
from custom_components.pumpsteer.v3.models import (
    ComfortPolicy,
    Observation,
    SafetyPolicy,
    SensorReading,
)


START = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
POLICY = ComfortPolicy(target_temperature=21.0)
SAFETY = SafetyPolicy(maximum_sensor_age=timedelta(minutes=10))


def _observation(
    now: datetime,
    *,
    indoor_c: float = 19.0,
    outdoor_c: float = -5.0,
    indoor_observed_at: datetime | None = None,
    outdoor_observed_at: datetime | None = None,
) -> Observation:
    return Observation(
        captured_at=now,
        indoor=SensorReading(
            indoor_c,
            indoor_observed_at or now,
            Unit.CELSIUS,
            "indoor",
        ),
        outdoor=SensorReading(
            outdoor_c,
            outdoor_observed_at or now,
            Unit.CELSIUS,
            "outdoor",
        ),
    )


def _step(
    engine: ControlEngine,
    observation: Observation | None,
    *,
    state: EngineState | None = None,
    now: datetime = START,
    dt: timedelta = timedelta(minutes=1),
    policy: ComfortPolicy = POLICY,
    shadow: bool = True,
):
    return engine.step(
        observation=observation,
        comfort_policy=policy,
        safety_policy=SAFETY,
        state=state or EngineState(),
        now_utc=now,
        dt=dt,
        shadow=shadow,
    )


def test_valid_critical_sensors_produce_shadow_comfort_decision() -> None:
    result = _step(ControlEngine(), _observation(START))

    assert result.requested_decision is not None
    assert result.requested_decision.state is ControlState.COMFORT
    assert result.requested_decision.heating_request > 0.0
    assert result.supervised_output.apply_physical is False
    assert ReasonCode.SHADOW_MODE in result.supervised_output.decision.reason_codes


def test_missing_optional_price_and_forecast_do_not_block_comfort() -> None:
    observation = _observation(START)
    assert observation.electricity_price is None
    assert observation.forecast_outdoor == ()

    result = _step(ControlEngine(), observation)

    assert result.comfort_result is not None
    assert result.input_reasons == ()
    assert result.supervised_output.fallback_active is False


def test_stale_indoor_sensor_enters_failsafe_and_passthrough() -> None:
    stale_at = START - SAFETY.maximum_sensor_age - timedelta(seconds=1)
    observation = _observation(START, indoor_observed_at=stale_at)

    result = _step(ControlEngine(), observation)

    assert result.requested_decision is None
    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == observation.outdoor.value
    assert result.supervised_output.apply_physical is False
    assert ReasonCode.INDOOR_SENSOR_INVALID in result.input_reasons
    assert ReasonCode.STALE_SENSOR in result.input_reasons


def test_future_critical_sensor_enters_failsafe_and_passthrough() -> None:
    future = START + timedelta(seconds=1)
    observation = _observation(START, indoor_observed_at=future)

    result = _step(ControlEngine(), observation)

    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == observation.outdoor.value
    assert ReasonCode.INDOOR_SENSOR_INVALID in result.input_reasons


def test_out_of_order_observation_enters_failsafe() -> None:
    old_capture = START - timedelta(minutes=1)
    observation = _observation(old_capture)

    result = _step(ControlEngine(), observation, now=START)

    assert result.supervised_output.decision.state is ControlState.FAILSAFE
    assert result.supervised_output.value == observation.outdoor.value
    assert ReasonCode.CRITICAL_SENSOR_INVALID in result.input_reasons


def test_non_finite_critical_reading_is_rejected_at_domain_boundary() -> None:
    try:
        SensorReading(float("nan"), START, Unit.CELSIUS, "indoor")
    except ValueError:
        pass
    else:
        raise AssertionError("NaN must not cross the SensorReading boundary")


def test_shadow_never_grants_physical_write_during_replay() -> None:
    engine = ControlEngine()
    state = EngineState()
    now = START

    for indoor_c in (19.0, 19.2, 19.5, 20.0, 20.5, 21.0):
        result = _step(
            engine,
            _observation(now, indoor_c=indoor_c),
            state=state,
            now=now,
        )
        assert result.apply_physical is False
        state = result.next_state
        now += timedelta(minutes=1)


def test_irregular_long_dt_is_bounded_and_output_remains_rate_limited() -> None:
    engine = ControlEngine()
    first = _step(engine, _observation(START, indoor_c=20.0))
    gap = timedelta(hours=2)
    later = START + gap
    second = _step(
        engine,
        _observation(later, indoor_c=18.0),
        state=first.next_state,
        now=later,
        dt=gap,
    )

    assert second.comfort_result is not None
    assert second.comfort_result.dt_bounded is True
    assert abs(second.supervised_output.value - first.supervised_output.value) <= 2.0


def test_identical_replay_produces_identical_results() -> None:
    trace = [20.5, 20.0, 19.5, 19.8, 20.2, 20.8]

    def replay():
        engine = ControlEngine()
        state = EngineState()
        now = START
        outputs = []
        for indoor_c in trace:
            result = _step(
                engine,
                _observation(now, indoor_c=indoor_c),
                state=state,
                now=now,
            )
            outputs.append(result)
            state = result.next_state
            now += timedelta(minutes=1)
        return outputs

    assert replay() == replay()


def test_target_update_changes_request_without_resetting_engine_state() -> None:
    engine = ControlEngine()
    first = _step(
        engine,
        _observation(START, indoor_c=20.0),
        policy=ComfortPolicy(target_temperature=20.0),
    )
    later = START + timedelta(minutes=1)
    raised = _step(
        engine,
        _observation(later, indoor_c=20.0),
        state=first.next_state,
        now=later,
        policy=ComfortPolicy(target_temperature=22.0),
    )

    assert first.requested_decision is not None
    assert raised.requested_decision is not None
    assert raised.requested_decision.heating_request > (
        first.requested_decision.heating_request
    )
    assert raised.next_state.comfort.last_step_at == later
