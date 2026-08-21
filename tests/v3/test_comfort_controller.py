"""Tests for the Home Assistant-independent V3 comfort controller."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custom_components.pumpsteer.v3 import (
    ComfortPolicy,
    Observation,
    SafetyPolicy,
    SensorReading,
    Unit,
)
from custom_components.pumpsteer.v3.control import (
    ComfortController,
    ComfortControllerConfig,
    ComfortControllerState,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def observation(indoor: float, now: datetime = NOW) -> Observation:
    return Observation(
        captured_at=now,
        indoor=SensorReading(indoor, now, Unit.CELSIUS, "indoor.test"),
        outdoor=SensorReading(-5.0, now, Unit.CELSIUS, "outdoor.test"),
    )


def step(
    controller: ComfortController,
    *,
    indoor: float,
    state: ComfortControllerState = ComfortControllerState(),
    now: datetime = NOW,
    dt: timedelta = timedelta(minutes=1),
    override_active: bool = False,
    safety: SafetyPolicy = SafetyPolicy(),
):
    return controller.step(
        observation=observation(indoor, now),
        policy=ComfortPolicy(target_temperature=21.0),
        safety_policy=safety,
        state=state,
        now_utc=now,
        dt=dt,
        override_active=override_active,
    )


def test_positive_error_produces_positive_bounded_heating_request() -> None:
    result = step(ComfortController(), indoor=20.0)

    assert result.comfort_error == pytest.approx(1.0)
    assert result.effective_error == pytest.approx(0.9)
    assert 0.0 < result.heating_request <= 15.0


@pytest.mark.parametrize("indoor", [20.9, 21.0, 21.1])
def test_deadband_produces_no_new_request_from_zero_state(indoor: float) -> None:
    result = step(ComfortController(), indoor=indoor)

    assert result.effective_error == 0.0
    assert result.heating_request == 0.0


def test_output_respects_narrower_safety_policy_limit() -> None:
    result = step(
        ComfortController(ComfortControllerConfig(proportional_gain=20.0)),
        indoor=18.0,
        safety=SafetyPolicy(maximum_heating_request=3.0),
    )

    assert result.heating_request == 3.0
    assert result.output_saturated


def test_conditional_integration_prevents_upper_windup() -> None:
    controller = ComfortController(
        ComfortControllerConfig(
            proportional_gain=10.0,
            integral_gain_per_hour=10.0,
            maximum_heating_request=2.0,
        )
    )
    result = step(controller, indoor=18.0)

    assert result.heating_request == 2.0
    assert result.integral_term == 0.0
    assert result.integrator_frozen


def test_override_freezes_existing_integral() -> None:
    state = ComfortControllerState(integral=1.25)
    result = step(
        ComfortController(),
        indoor=20.0,
        state=state,
        override_active=True,
    )

    assert result.integral_term == 1.25
    assert result.next_state.integral == 1.25
    assert result.integrator_frozen


def test_long_dt_is_bounded_before_integration() -> None:
    config = ComfortControllerConfig(
        proportional_gain=0.0,
        integral_gain_per_hour=6.0,
        maximum_dt=timedelta(minutes=5),
    )
    result = step(
        ComfortController(config),
        indoor=19.9,
        dt=timedelta(hours=1),
    )

    assert result.dt_bounded
    assert result.integral_term == pytest.approx(0.5)


@pytest.mark.parametrize("dt", [timedelta(0), timedelta(seconds=-1)])
def test_non_positive_dt_is_rejected(dt: timedelta) -> None:
    with pytest.raises(ValueError, match="dt must be positive"):
        step(ComfortController(), indoor=20.0, dt=dt)


def test_elapsed_time_must_match_explicit_dt() -> None:
    state = ComfortControllerState(integral=0.0, last_step_at=NOW)
    later = NOW + timedelta(minutes=2)

    with pytest.raises(ValueError, match="dt must match"):
        step(
            ComfortController(),
            indoor=20.0,
            state=state,
            now=later,
            dt=timedelta(minutes=1),
        )


def test_non_utc_control_time_is_rejected() -> None:
    non_utc = datetime(2026, 1, 15, 13, 0, tzinfo=timezone(timedelta(hours=1)))

    with pytest.raises(ValueError, match="must use UTC"):
        step(ComfortController(), indoor=20.0, now=non_utc)


def test_state_and_result_are_immutable() -> None:
    result = step(ComfortController(), indoor=20.0)

    with pytest.raises(AttributeError):
        result.next_state.integral = 99.0


def test_controller_is_deterministic_for_identical_inputs() -> None:
    controller = ComfortController()
    first = step(controller, indoor=20.0)
    second = step(controller, indoor=20.0)

    assert first == second
