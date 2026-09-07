"""Testable shadow runtime at the Home Assistant adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from ..control.engine import ControlEngine, EngineResult, EngineState
from ..control.supervisor import SupervisedOutput
from ..enums import Unit
from ..models import (
    ComfortPolicy,
    ControlDecision,
    Observation,
    SafetyPolicy,
    SensorReading,
)
from ..pricing import DEFAULT_SAVING_LEVEL, normalize_saving_level
from ..validation import aware_datetime, finite_float, supported_unit


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Minimal user configuration for the V3 shadow runtime."""

    indoor_entity: str
    outdoor_entity: str
    target_temperature: float = 21.0
    saving_level: int = DEFAULT_SAVING_LEVEL
    update_interval: timedelta = timedelta(minutes=1)

    def __post_init__(self) -> None:
        for name in ("indoor_entity", "outdoor_entity"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty entity ID")
        target = finite_float(self.target_temperature, "target_temperature")
        if not 5.0 <= target <= 35.0:
            raise ValueError("target_temperature must be between 5 and 35 °C")
        object.__setattr__(self, "target_temperature", target)
        object.__setattr__(
            self,
            "saving_level",
            normalize_saving_level(self.saving_level),
        )
        if not isinstance(self.update_interval, timedelta):
            raise TypeError("update_interval must be a timedelta")
        if self.update_interval <= timedelta(0):
            raise ValueError("update_interval must be positive")


@dataclass(frozen=True, slots=True)
class RawState:
    """Platform-neutral state read from a Home Assistant entity."""

    value: object
    observed_at: datetime
    unit: Unit | str
    source: str


class StateProvider(Protocol):
    """Read-only state boundary implemented by the Home Assistant adapter."""

    def get_state(self, entity_id: str) -> RawState | None:
        """Return the latest state without performing I/O."""


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Observable result of one complete shadow cycle."""

    observation: Observation | None
    engine_result: EngineResult
    error: str | None = None

    @property
    def requested(self) -> ControlDecision | None:
        """Return the engine request for diagnostics."""
        return self.engine_result.requested_decision

    @property
    def supervised(self) -> SupervisedOutput:
        """Return the engine-owned supervised output."""
        return self.engine_result.supervised_output


class NullOutput:
    """Shadow-only output sink that never performs a physical write."""

    def __init__(self) -> None:
        self.latest: SupervisedOutput | None = None
        self.publish_count = 0

    async def async_publish(self, output: SupervisedOutput) -> None:
        """Record a supervised shadow result without touching an actuator."""
        if output.apply_physical:
            raise ValueError("NullOutput only accepts shadow outputs")
        self.latest = output
        self.publish_count += 1


class PumpSteerRuntime:
    """Coordinate state conversion, engine execution and shadow publication."""

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        states: StateProvider,
        engine: ControlEngine,
        safety_policy: SafetyPolicy | None = None,
        output: NullOutput | None = None,
    ) -> None:
        self._config = config
        self._states = states
        self._engine = engine
        self._safety = safety_policy or SafetyPolicy()
        self._output = output or NullOutput()
        self._latest: RuntimeResult | None = None
        self._engine_state = EngineState()
        self._last_update_at: datetime | None = None

    @property
    def config(self) -> RuntimeConfig:
        """Return current immutable runtime configuration."""
        return self._config

    @property
    def latest(self) -> RuntimeResult | None:
        """Return the latest complete cycle result."""
        return self._latest

    @property
    def output(self) -> NullOutput:
        """Return the shadow output sink."""
        return self._output

    def set_target_temperature(self, target_temperature: float) -> None:
        """Update only the user-facing target while preserving source selection."""
        self._config = replace(
            self._config,
            target_temperature=target_temperature,
        )

    def set_saving_level(self, saving_level: object) -> None:
        """Update economic intent without changing any control authority."""
        self._config = replace(
            self._config,
            saving_level=normalize_saving_level(saving_level),
        )

    async def async_update(self, now: datetime) -> RuntimeResult:
        """Run one cycle through the canonical engine in mandatory shadow mode."""
        now = aware_datetime(now, "now")
        if now.utcoffset() != timedelta(0):
            raise ValueError("now must use UTC")
        dt = (
            self._config.update_interval
            if self._last_update_at is None
            else now - self._last_update_at
        )
        if dt <= timedelta(0):
            raise ValueError("now must be later than the previous update")
        fallback_outdoor = _read_optional_temperature(
            self._states,
            self._config.outdoor_entity,
        )
        try:
            observation = build_observation(
                states=self._states,
                config=self._config,
                now=now,
            )
        except Exception as err:
            observation = None
            input_error = f"{type(err).__name__}: {err}"
        else:
            input_error = None

        try:
            engine_result = self._engine.step(
                observation=observation,
                comfort_policy=_comfort_policy(self._config.target_temperature),
                safety_policy=self._safety,
                state=self._engine_state,
                now_utc=now,
                dt=dt,
                shadow=True,
                fallback_outdoor_temperature=fallback_outdoor,
            )
        except Exception as err:
            engine_result = self._engine.fail_safe(
                safety_policy=self._safety,
                state=self._engine_state,
                now_utc=now,
                shadow=True,
                fallback_outdoor_temperature=fallback_outdoor,
            )
            engine_error = f"{type(err).__name__}: {err}"
            input_error = (
                f"{input_error}; {engine_error}" if input_error else engine_error
            )
        if engine_result.apply_physical:
            raise RuntimeError("V3 HA runtime must remain in shadow mode")
        result = RuntimeResult(
            observation=observation,
            engine_result=engine_result,
            error=input_error,
        )
        await self._output.async_publish(engine_result.supervised_output)
        self._engine_state = engine_result.next_state
        self._last_update_at = now
        self._latest = result
        return result


def build_observation(
    *,
    states: StateProvider,
    config: RuntimeConfig,
    now: datetime,
) -> Observation:
    """Translate current platform states into a validated domain observation."""
    now = aware_datetime(now, "now")
    indoor = _required_temperature(states, config.indoor_entity)
    outdoor = _required_temperature(states, config.outdoor_entity)
    return Observation(captured_at=now, indoor=indoor, outdoor=outdoor)


def _required_temperature(states: StateProvider, entity_id: str) -> SensorReading:
    raw = states.get_state(entity_id)
    if raw is None:
        raise ValueError(f"required entity is missing: {entity_id}")
    if supported_unit(raw.unit) is not Unit.CELSIUS:
        raise ValueError(f"temperature entity must use °C: {entity_id}")
    return SensorReading(
        value=finite_float(raw.value, entity_id),
        observed_at=raw.observed_at,
        unit=Unit.CELSIUS,
        source=raw.source,
    )


def _read_optional_temperature(states: StateProvider, entity_id: str) -> float | None:
    """Return a usable outdoor fallback without hiding conversion failures."""
    try:
        return _required_temperature(states, entity_id).value
    except (TypeError, ValueError):
        return None


def _comfort_policy(target: float) -> ComfortPolicy:
    return ComfortPolicy(
        target_temperature=target,
        minimum_temperature=max(5.0, target - 1.5),
        maximum_temperature=min(35.0, target + 2.0),
    )
