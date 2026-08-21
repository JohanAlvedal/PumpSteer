"""Physics and reproducibility tests for the PumpSteer V3 simulator."""

from __future__ import annotations

import math

from custom_components.pumpsteer.v3.simulation import (
    ActuatorConfig,
    BuildingConfig,
    Disturbance,
    SensorFault,
    ThermalSimulator,
)


def _run(simulator: ThermalSimulator, command: float, minutes: int, outdoor: float):
    return [
        simulator.step(command, Disturbance(outdoor), duration_seconds=60.0)
        for _ in range(minutes)
    ]


def test_heat_input_has_positive_temperature_sign() -> None:
    unheated = ThermalSimulator(BuildingConfig(), seed=1)
    heated = ThermalSimulator(
        BuildingConfig(),
        ActuatorConfig(
            command_delay_seconds=0,
            source_time_constant_seconds=0,
            emitter_time_constant_seconds=0,
        ),
        seed=1,
    )

    _run(unheated, 0.0, 60, outdoor=5.0)
    _run(heated, 1.0, 60, outdoor=5.0)

    assert heated.indoor_c > unheated.indoor_c


def test_envelope_loss_cools_towards_outdoor_temperature() -> None:
    simulator = ThermalSimulator(
        BuildingConfig(initial_indoor_c=20.0),
        seed=2,
    )
    samples = _run(simulator, 0.0, 180, outdoor=0.0)

    assert 0.0 < samples[-1].indoor_c < samples[0].indoor_c < 20.0
    assert all(sample.envelope_loss_kw > 0.0 for sample in samples)


def test_seeded_sensor_noise_is_reproducible() -> None:
    fault = SensorFault(gaussian_noise_std_c=0.2, dropout_probability=0.1)
    first = ThermalSimulator(BuildingConfig(), seed=42)
    second = ThermalSimulator(BuildingConfig(), seed=42)

    trace_a = [
        first.step(0.4, Disturbance(3.0), sensor_fault=fault).measured_indoor_c
        for _ in range(50)
    ]
    trace_b = [
        second.step(0.4, Disturbance(3.0), sensor_fault=fault).measured_indoor_c
        for _ in range(50)
    ]

    assert trace_a == trace_b
    assert any(value is None for value in trace_a)


def test_command_and_heat_are_saturated() -> None:
    maximum_kw = 5.0
    simulator = ThermalSimulator(
        BuildingConfig(),
        ActuatorConfig(
            maximum_heat_kw=maximum_kw,
            source_time_constant_seconds=0,
            emitter_time_constant_seconds=0,
        ),
    )

    high = simulator.step(9.0, Disturbance(10.0), duration_seconds=60.0)
    low = simulator.step(-4.0, Disturbance(10.0), duration_seconds=60.0)

    assert high.requested_command == 1.0
    assert 0.0 <= high.source_heat_kw <= maximum_kw
    assert low.requested_command == 0.0
    assert 0.0 <= low.source_heat_kw <= maximum_kw


def test_delay_slew_and_afterheat_are_observable() -> None:
    simulator = ThermalSimulator(
        BuildingConfig(),
        ActuatorConfig(
            maximum_heat_kw=8.0,
            command_delay_seconds=120.0,
            maximum_slew_kw_per_minute=2.0,
            source_time_constant_seconds=0.0,
            emitter_time_constant_seconds=180.0,
        ),
    )

    first = simulator.step(1.0, Disturbance(10.0), duration_seconds=60.0)
    second = simulator.step(1.0, Disturbance(10.0), duration_seconds=60.0)
    third = simulator.step(1.0, Disturbance(10.0), duration_seconds=60.0)
    assert first.source_heat_kw == 0.0
    assert second.source_heat_kw == 0.0
    assert 0.0 < third.source_heat_kw <= 2.0

    simulator.step(0.0, Disturbance(10.0), duration_seconds=180.0)
    off = simulator.step(0.0, Disturbance(10.0), duration_seconds=60.0)
    assert off.delivered_heat_kw > 0.0


def test_internal_substeps_keep_long_run_stable_and_finite() -> None:
    simulator = ThermalSimulator(
        BuildingConfig(
            air_capacitance_kwh_per_k=1.5,
            envelope_conductance_kw_per_k=0.25,
            mass_capacitance_kwh_per_k=25.0,
            air_mass_conductance_kw_per_k=0.8,
            heat_to_mass_fraction=0.6,
        ),
        seed=3,
    )

    for hour in range(24 * 7):
        outdoor = -8.0 + 5.0 * math.sin(hour * math.pi / 12.0)
        sample = simulator.step(
            0.55,
            Disturbance(outdoor, solar_gain_kw=max(0.0, math.sin(hour * math.pi / 12))),
            duration_seconds=3600.0,
        )
        assert math.isfinite(sample.indoor_c)
        assert sample.mass_c is not None and math.isfinite(sample.mass_c)
        assert -30.0 < sample.indoor_c < 60.0


def test_floor_heating_air_response_is_slower_than_light_radiator() -> None:
    actuator = ActuatorConfig(
        maximum_heat_kw=8.0,
        source_time_constant_seconds=0.0,
        emitter_time_constant_seconds=0.0,
    )
    radiator = ThermalSimulator(
        BuildingConfig(
            air_capacitance_kwh_per_k=2.0,
            envelope_conductance_kw_per_k=0.1,
        ),
        actuator,
    )
    floor = ThermalSimulator(
        BuildingConfig(
            air_capacitance_kwh_per_k=2.0,
            envelope_conductance_kw_per_k=0.1,
            mass_capacitance_kwh_per_k=30.0,
            air_mass_conductance_kw_per_k=0.8,
            heat_to_mass_fraction=0.9,
        ),
        actuator,
    )

    radiator_start = radiator.indoor_c
    floor_start = floor.indoor_c
    _run(radiator, 1.0, 120, outdoor=10.0)
    _run(floor, 1.0, 120, outdoor=10.0)

    assert radiator.indoor_c - radiator_start > floor.indoor_c - floor_start


def test_fault_hooks_do_not_modify_true_temperature() -> None:
    baseline = ThermalSimulator(BuildingConfig(), seed=7)
    faulty = ThermalSimulator(BuildingConfig(), seed=7)
    fault = SensorFault(bias_c=4.0, spike_c=10.0, stuck_at_c=99.0)

    base = baseline.step(0.5, Disturbance(0.0))
    observed = faulty.step(0.5, Disturbance(0.0), sensor_fault=fault)

    assert observed.indoor_c == base.indoor_c
    assert observed.measured_indoor_c == 99.0
