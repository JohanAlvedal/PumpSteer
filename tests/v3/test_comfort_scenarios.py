"""Closed-loop comfort and safety scenarios for the PumpSteer V3 core."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from custom_components.pumpsteer.v3.control import (
    ComfortController,
    ComfortControllerState,
)
from custom_components.pumpsteer.v3.control.supervisor import (
    SupervisorPolicy,
    supervise_output,
)
from custom_components.pumpsteer.v3.enums import ControlState, ReasonCode, Unit
from custom_components.pumpsteer.v3.models import (
    ComfortPolicy,
    ControlDecision,
    Observation,
    SafetyPolicy,
    SensorReading,
)
from custom_components.pumpsteer.v3.simulation import (
    ActuatorConfig,
    BuildingConfig,
    Disturbance,
    ThermalSimulator,
)


START = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
TARGET_C = 21.0


def _observation(now: datetime, indoor_c: float, outdoor_c: float) -> Observation:
    return Observation(
        captured_at=now,
        indoor=SensorReading(indoor_c, now, Unit.CELSIUS, "simulated_indoor"),
        outdoor=SensorReading(outdoor_c, now, Unit.CELSIUS, "simulated_outdoor"),
    )


def _closed_loop(
    building: BuildingConfig,
    *,
    hours: int,
    outdoor_c: float = -5.0,
) -> tuple[list[float], list[float]]:
    """Run comfort control against a building with a thin actuator adapter.

    The domain heating request is expressed in virtual-temperature degrees.
    Dividing by its hard safety maximum converts it into the simulator's
    normalized actuator command without embedding heat-pump details in the
    production controller.
    """
    actuator = ActuatorConfig(
        maximum_heat_kw=8.0,
        command_delay_seconds=120.0,
        maximum_slew_kw_per_minute=1.5,
        source_time_constant_seconds=90.0,
        emitter_time_constant_seconds=300.0 if building.has_mass_node else 90.0,
    )
    simulator = ThermalSimulator(building, actuator, seed=11)
    controller = ComfortController()
    state = ComfortControllerState()
    policy = ComfortPolicy(target_temperature=TARGET_C)
    safety = SafetyPolicy(maximum_heating_request=15.0)
    temperatures: list[float] = []
    requests: list[float] = []
    now = START
    dt = timedelta(minutes=1)

    for _ in range(hours * 60):
        result = controller.step(
            observation=_observation(now, simulator.indoor_c, outdoor_c),
            policy=policy,
            safety_policy=safety,
            state=state,
            now_utc=now,
            dt=dt,
        )
        state = result.next_state
        command = result.heating_request / safety.maximum_heating_request
        sample = simulator.step(
            command,
            Disturbance(outdoor_c, internal_gain_kw=0.2),
            duration_seconds=dt.total_seconds(),
        )
        temperatures.append(sample.indoor_c)
        requests.append(result.heating_request)
        now += dt

    return temperatures, requests


def test_colder_house_requests_more_heat() -> None:
    controller = ComfortController()
    policy = ComfortPolicy(target_temperature=TARGET_C)
    safety = SafetyPolicy()
    dt = timedelta(minutes=1)

    cold = controller.step(
        observation=_observation(START, 18.0, -5.0),
        policy=policy,
        safety_policy=safety,
        state=ComfortControllerState(),
        now_utc=START,
        dt=dt,
    )
    mild = controller.step(
        observation=_observation(START, 20.5, -5.0),
        policy=policy,
        safety_policy=safety,
        state=ComfortControllerState(),
        now_utc=START,
        dt=dt,
    )

    assert cold.heating_request > mild.heating_request >= 0.0


def test_light_radiator_closed_loop_converges_near_target() -> None:
    temperatures, requests = _closed_loop(
        BuildingConfig(
            air_capacitance_kwh_per_k=3.0,
            envelope_conductance_kw_per_k=0.12,
            initial_indoor_c=18.0,
        ),
        hours=72,
    )

    final_day = temperatures[-24 * 60 :]
    assert abs(sum(final_day) / len(final_day) - TARGET_C) < 0.35
    assert max(final_day) - min(final_day) < 0.5
    assert all(0.0 <= request <= 15.0 for request in requests)


def test_heavy_floor_closed_loop_converges_without_oscillation() -> None:
    temperatures, requests = _closed_loop(
        BuildingConfig(
            air_capacitance_kwh_per_k=2.5,
            envelope_conductance_kw_per_k=0.12,
            mass_capacitance_kwh_per_k=30.0,
            air_mass_conductance_kw_per_k=0.8,
            heat_to_mass_fraction=0.85,
            initial_indoor_c=19.0,
            initial_mass_c=19.0,
        ),
        hours=24 * 10,
    )

    final_two_days = temperatures[-48 * 60 :]
    first_day_error = abs(sum(temperatures[:1440]) / 1440 - TARGET_C)
    final_error = abs(sum(final_two_days) / len(final_two_days) - TARGET_C)
    assert final_error < first_day_error
    assert final_error < 0.45
    assert max(final_two_days) - min(final_two_days) < 0.6
    assert all(math.isfinite(value) for value in temperatures + requests)


def test_supervisor_bounds_and_slew_limits_output() -> None:
    safety = SafetyPolicy(
        minimum_virtual_temperature=-20.0,
        maximum_virtual_temperature=25.0,
        maximum_heating_request=15.0,
    )
    policy = SupervisorPolicy(
        maximum_slew_per_minute=0.5,
        maximum_step=1.0,
        quantum=0.1,
    )
    previous = None
    values: list[float] = []

    for minute in range(8):
        now = START + timedelta(minutes=minute)
        request = ControlDecision.create(
            decided_at=now,
            state=ControlState.COMFORT,
            outdoor_temperature=5.0,
            heating_request=15.0,
            reason_codes=(ReasonCode.COMFORT_BELOW_TARGET,),
        )
        output = supervise_output(
            request,
            safety=safety,
            policy=policy,
            now=now,
            previous=previous,
        )
        values.append(output.value)
        previous = output

    assert all(-20.0 <= value <= 25.0 for value in values)
    assert all(abs(b - a) <= 0.5 + 1e-9 for a, b in zip(values, values[1:]))


def test_long_restart_gap_is_dt_bounded_without_integral_jump() -> None:
    controller = ComfortController()
    policy = ComfortPolicy(target_temperature=TARGET_C)
    safety = SafetyPolicy()
    initial = ComfortControllerState(integral=2.0, last_step_at=START)
    gap = timedelta(hours=3)
    now = START + gap

    after_gap = controller.step(
        observation=_observation(now, 20.0, -5.0),
        policy=policy,
        safety_policy=safety,
        state=initial,
        now_utc=now,
        dt=gap,
    )
    reference = controller.step(
        observation=_observation(now, 20.0, -5.0),
        policy=policy,
        safety_policy=safety,
        state=initial,
        now_utc=now,
        dt=gap,
    )

    assert after_gap.dt_bounded is True
    assert after_gap.heating_request == reference.heating_request
    maximum_integral_change = (
        controller.config.integral_gain_per_hour
        * after_gap.effective_error
        * controller.config.maximum_dt.total_seconds()
        / 3600.0
    )
    assert (
        abs(after_gap.integral_term - initial.integral)
        <= abs(maximum_integral_change) + 1e-12
    )


def test_override_freezes_integrator_without_hiding_comfort_need() -> None:
    controller = ComfortController()
    policy = ComfortPolicy(target_temperature=TARGET_C)
    safety = SafetyPolicy()
    state = ComfortControllerState(integral=1.5)
    now = START

    for _ in range(180):
        result = controller.step(
            observation=_observation(now, 18.0, -5.0),
            policy=policy,
            safety_policy=safety,
            state=state,
            now_utc=now,
            dt=timedelta(minutes=1),
            override_active=True,
        )
        state = result.next_state
        now += timedelta(minutes=1)

    assert state.integral == 1.5
    assert result.integrator_frozen is True
    assert result.heating_request > 0.0


def test_supervisor_critical_sensor_failure_bypasses_old_manipulation() -> None:
    safety = SafetyPolicy()
    policy = SupervisorPolicy(quantum=0.5)
    previous_request = ControlDecision.create(
        decided_at=START,
        state=ControlState.COMFORT,
        outdoor_temperature=-5.0,
        heating_request=12.0,
        reason_codes=(ReasonCode.COMFORT_BELOW_TARGET,),
    )
    previous = supervise_output(
        previous_request,
        safety=safety,
        policy=policy,
        now=START,
    )

    failed = supervise_output(
        previous_request,
        safety=safety,
        policy=policy,
        now=START + timedelta(seconds=1),
        previous=previous,
        critical_input_valid=False,
        fallback_outdoor_temperature=-5.0,
    )

    assert failed.fallback_active is True
    assert failed.decision.state is ControlState.FAILSAFE
    assert failed.value == -5.0
    assert failed.apply_physical is True
    assert ReasonCode.CRITICAL_SENSOR_INVALID in failed.decision.reason_codes
