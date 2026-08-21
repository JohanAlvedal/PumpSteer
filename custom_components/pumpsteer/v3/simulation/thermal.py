"""Small deterministic building and heating-system simulator.

The simulator is deliberately independent from Home Assistant.  It is not a
design tool and does not attempt to reproduce every heat-pump detail.  Its
purpose is to exercise control and safety logic against models with explicit
units, signs, delays, limits, emitter inertia, disturbances, and sensor faults.

Temperatures are degrees Celsius, powers are kW, thermal capacitances are
kWh/K, conductances are kW/K, and time constants are seconds.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import random
from typing import Deque


@dataclass(frozen=True)
class BuildingConfig:
    """Parameters for either a 1R1C or a two-node thermal building model."""

    air_capacitance_kwh_per_k: float = 3.0
    envelope_conductance_kw_per_k: float = 0.12
    mass_capacitance_kwh_per_k: float | None = None
    air_mass_conductance_kw_per_k: float = 0.0
    heat_to_mass_fraction: float = 0.0
    initial_indoor_c: float = 20.0
    initial_mass_c: float | None = None

    def __post_init__(self) -> None:
        if self.air_capacitance_kwh_per_k <= 0:
            raise ValueError("air_capacitance_kwh_per_k must be positive")
        if self.envelope_conductance_kw_per_k < 0:
            raise ValueError("envelope_conductance_kw_per_k cannot be negative")
        if self.mass_capacitance_kwh_per_k is not None:
            if self.mass_capacitance_kwh_per_k <= 0:
                raise ValueError("mass_capacitance_kwh_per_k must be positive")
            if self.air_mass_conductance_kw_per_k <= 0:
                raise ValueError("a two-node model requires positive coupling")
        if not 0.0 <= self.heat_to_mass_fraction <= 1.0:
            raise ValueError("heat_to_mass_fraction must be in [0, 1]")

    @property
    def has_mass_node(self) -> bool:
        """Return whether the configuration represents a two-node model."""
        return self.mass_capacitance_kwh_per_k is not None


@dataclass(frozen=True)
class ActuatorConfig:
    """Heat-source and emitter response parameters."""

    maximum_heat_kw: float = 8.0
    command_delay_seconds: float = 0.0
    maximum_slew_kw_per_minute: float = 8.0
    source_time_constant_seconds: float = 30.0
    emitter_time_constant_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.maximum_heat_kw <= 0:
            raise ValueError("maximum_heat_kw must be positive")
        if self.command_delay_seconds < 0:
            raise ValueError("command_delay_seconds cannot be negative")
        if self.maximum_slew_kw_per_minute <= 0:
            raise ValueError("maximum_slew_kw_per_minute must be positive")
        if self.source_time_constant_seconds < 0:
            raise ValueError("source_time_constant_seconds cannot be negative")
        if self.emitter_time_constant_seconds < 0:
            raise ValueError("emitter_time_constant_seconds cannot be negative")


@dataclass(frozen=True)
class Disturbance:
    """External conditions and uncontrolled heat gains for one step."""

    outdoor_c: float
    solar_gain_kw: float = 0.0
    internal_gain_kw: float = 0.0


@dataclass(frozen=True)
class SensorFault:
    """Optional indoor-sensor noise and fault injection."""

    gaussian_noise_std_c: float = 0.0
    bias_c: float = 0.0
    dropout_probability: float = 0.0
    stuck_at_c: float | None = None
    spike_c: float = 0.0

    def __post_init__(self) -> None:
        if self.gaussian_noise_std_c < 0:
            raise ValueError("gaussian_noise_std_c cannot be negative")
        if not 0.0 <= self.dropout_probability <= 1.0:
            raise ValueError("dropout_probability must be in [0, 1]")


@dataclass(frozen=True)
class SimulationSample:
    """Observable simulator state after a completed step."""

    elapsed_seconds: float
    indoor_c: float
    mass_c: float | None
    measured_indoor_c: float | None
    requested_command: float
    delayed_command: float
    source_heat_kw: float
    delivered_heat_kw: float
    envelope_loss_kw: float
    disturbance_gain_kw: float


class ThermalSimulator:
    """Seeded simulator combining a building, actuator, and sensor model."""

    _MAX_INTEGRATION_STEP_SECONDS = 30.0

    def __init__(
        self,
        building: BuildingConfig,
        actuator: ActuatorConfig | None = None,
        *,
        seed: int = 0,
    ) -> None:
        self.building = building
        self.actuator = actuator or ActuatorConfig()
        self.elapsed_seconds = 0.0
        self.indoor_c = float(building.initial_indoor_c)
        self.mass_c = (
            float(
                building.initial_mass_c
                if building.initial_mass_c is not None
                else building.initial_indoor_c
            )
            if building.has_mass_node
            else None
        )
        self.source_heat_kw = 0.0
        self.delivered_heat_kw = 0.0
        self._rng = random.Random(seed)
        self._commands: Deque[tuple[float, float]] = deque([(0.0, 0.0)])

    def step(
        self,
        command: float,
        disturbance: Disturbance,
        *,
        duration_seconds: float = 60.0,
        sensor_fault: SensorFault | None = None,
    ) -> SimulationSample:
        """Advance the simulation and return the resulting sample.

        A command of zero requests no compressor heat and one requests the
        configured maximum.  Values outside this interval are saturated.
        Long caller steps are divided internally to keep Euler integration
        stable and to make actuator delays physically meaningful.
        """
        if duration_seconds <= 0 or not math.isfinite(duration_seconds):
            raise ValueError("duration_seconds must be finite and positive")
        if not math.isfinite(command):
            raise ValueError("command must be finite")
        requested = min(1.0, max(0.0, command))
        self._commands.append((self.elapsed_seconds, requested))

        steps = max(
            1,
            math.ceil(duration_seconds / self._MAX_INTEGRATION_STEP_SECONDS),
        )
        substep_seconds = duration_seconds / steps
        delayed = 0.0
        envelope_loss_kw = 0.0
        disturbance_gain_kw = disturbance.solar_gain_kw + disturbance.internal_gain_kw

        for _ in range(steps):
            delayed = self._delayed_command()
            self._advance_actuator(delayed, substep_seconds)
            envelope_loss_kw = self._advance_building(
                disturbance,
                substep_seconds,
            )
            self.elapsed_seconds += substep_seconds

        self._discard_old_commands()
        measured = self._measure(sensor_fault or SensorFault())
        return SimulationSample(
            elapsed_seconds=self.elapsed_seconds,
            indoor_c=self.indoor_c,
            mass_c=self.mass_c,
            measured_indoor_c=measured,
            requested_command=requested,
            delayed_command=delayed,
            source_heat_kw=self.source_heat_kw,
            delivered_heat_kw=self.delivered_heat_kw,
            envelope_loss_kw=envelope_loss_kw,
            disturbance_gain_kw=disturbance_gain_kw,
        )

    def _delayed_command(self) -> float:
        cutoff = self.elapsed_seconds - self.actuator.command_delay_seconds
        delayed = 0.0
        for timestamp, command in self._commands:
            if timestamp <= cutoff:
                delayed = command
            else:
                break
        return delayed

    def _discard_old_commands(self) -> None:
        cutoff = self.elapsed_seconds - self.actuator.command_delay_seconds
        while len(self._commands) > 1 and self._commands[1][0] <= cutoff:
            self._commands.popleft()

    @staticmethod
    def _first_order(current: float, target: float, dt: float, tau: float) -> float:
        if tau <= 0:
            return target
        fraction = 1.0 - math.exp(-dt / tau)
        return current + (target - current) * fraction

    def _advance_actuator(self, delayed_command: float, dt: float) -> None:
        target_kw = delayed_command * self.actuator.maximum_heat_kw
        lagged_target = self._first_order(
            self.source_heat_kw,
            target_kw,
            dt,
            self.actuator.source_time_constant_seconds,
        )
        max_change = self.actuator.maximum_slew_kw_per_minute * dt / 60.0
        change = min(max_change, max(-max_change, lagged_target - self.source_heat_kw))
        self.source_heat_kw = min(
            self.actuator.maximum_heat_kw,
            max(0.0, self.source_heat_kw + change),
        )
        # Emitter lag stores heat and therefore produces a natural afterheat tail.
        self.delivered_heat_kw = self._first_order(
            self.delivered_heat_kw,
            self.source_heat_kw,
            dt,
            self.actuator.emitter_time_constant_seconds,
        )
        self.delivered_heat_kw = min(
            self.actuator.maximum_heat_kw,
            max(0.0, self.delivered_heat_kw),
        )

    def _advance_building(self, disturbance: Disturbance, dt: float) -> float:
        cfg = self.building
        hours = dt / 3600.0
        envelope_loss_kw = cfg.envelope_conductance_kw_per_k * (
            self.indoor_c - disturbance.outdoor_c
        )
        gains_kw = disturbance.solar_gain_kw + disturbance.internal_gain_kw

        if self.mass_c is None:
            net_air_kw = self.delivered_heat_kw + gains_kw - envelope_loss_kw
            self.indoor_c += (net_air_kw / cfg.air_capacitance_kwh_per_k) * hours
            return envelope_loss_kw

        coupling_kw = cfg.air_mass_conductance_kw_per_k * (self.mass_c - self.indoor_c)
        heat_to_mass_kw = self.delivered_heat_kw * cfg.heat_to_mass_fraction
        heat_to_air_kw = self.delivered_heat_kw - heat_to_mass_kw
        net_air_kw = heat_to_air_kw + gains_kw - envelope_loss_kw + coupling_kw
        net_mass_kw = heat_to_mass_kw - coupling_kw
        self.indoor_c += (net_air_kw / cfg.air_capacitance_kwh_per_k) * hours
        self.mass_c += (net_mass_kw / float(cfg.mass_capacitance_kwh_per_k)) * hours
        return envelope_loss_kw

    def _measure(self, fault: SensorFault) -> float | None:
        if self._rng.random() < fault.dropout_probability:
            return None
        if fault.stuck_at_c is not None:
            return fault.stuck_at_c
        noise = self._rng.gauss(0.0, fault.gaussian_noise_std_c)
        return self.indoor_c + fault.bias_c + fault.spike_c + noise
