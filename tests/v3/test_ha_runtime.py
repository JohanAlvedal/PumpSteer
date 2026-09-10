"""Tests for the platform-neutral parts of the PumpSteer V3 HA runtime."""

import asyncio

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3 import (
    ControlState,
    Unit,
)
from custom_components.pumpsteer.v3.control.engine import ControlEngine
from custom_components.pumpsteer.v3.ha import (
    NullOutput,
    PumpSteerRuntime,
    RawState,
    RuntimeConfig,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeStates:
    def __init__(self, values: dict[str, RawState]) -> None:
        self.values = values

    def get_state(self, entity_id: str) -> RawState | None:
        return self.values.get(entity_id)


class FakeEngine:
    def __init__(self) -> None:
        self.targets: list[float] = []
        self.dts: list[timedelta] = []
        self._engine = ControlEngine()

    def step(self, **kwargs):
        comfort_policy = kwargs["comfort_policy"]
        self.targets.append(comfort_policy.target_temperature)
        self.dts.append(kwargs["dt"])
        return self._engine.step(**kwargs)

    def fail_safe(self, **kwargs):
        return self._engine.fail_safe(**kwargs)


class FailingEngine(ControlEngine):
    def step(self, **kwargs):
        raise RuntimeError("simulated engine failure")


class ActiveOutput:
    physical_enabled = True

    def __init__(self, *, fail: bool = False) -> None:
        self.outputs = []
        self.fail = fail
        self.shutdown_count = 0

    async def async_publish(self, output) -> None:
        if self.fail:
            raise RuntimeError("simulated output failure")
        self.outputs.append(output)

    async def async_shutdown(self) -> None:
        self.shutdown_count += 1


def state(value: object, entity_id: str, age_minutes: int = 0) -> RawState:
    return RawState(
        value=value,
        observed_at=NOW - timedelta(minutes=age_minutes),
        unit=Unit.CELSIUS,
        source=entity_id,
    )


def runtime(states: FakeStates, engine: FakeEngine | None = None) -> PumpSteerRuntime:
    return PumpSteerRuntime(
        config=RuntimeConfig("sensor.indoor", "sensor.outdoor", 21.0),
        states=states,
        engine=engine or ControlEngine(),
    )


def test_valid_cycle_builds_observation_and_never_applies_output() -> None:
    output = NullOutput()
    instance = PumpSteerRuntime(
        config=RuntimeConfig("sensor.indoor", "sensor.outdoor", 21.0),
        states=FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor"),
                "sensor.outdoor": state(-5.0, "sensor.outdoor"),
            }
        ),
        engine=FakeEngine(),
        output=output,
    )

    result = asyncio.run(instance.async_update(NOW))

    assert result.error is None
    assert result.observation is not None
    assert result.observation.indoor.value == 20.0
    assert not result.supervised.apply_physical
    assert output.latest is result.supervised
    assert output.publish_count == 1


def test_explicit_active_adapter_receives_physical_comfort_output() -> None:
    output = ActiveOutput()
    instance = PumpSteerRuntime(
        config=RuntimeConfig("sensor.indoor", "sensor.outdoor", 21.0),
        states=FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor"),
                "sensor.outdoor": state(-5.0, "sensor.outdoor"),
            }
        ),
        engine=ControlEngine(),
        output=output,
    )

    result = asyncio.run(instance.async_update(NOW))

    assert instance.physical_control_enabled is True
    assert result.error is None
    assert result.supervised.apply_physical is True
    assert output.outputs == [result.supervised]


def test_active_adapter_receives_bypass_for_stale_critical_input() -> None:
    output = ActiveOutput()
    instance = PumpSteerRuntime(
        config=RuntimeConfig("sensor.indoor", "sensor.outdoor", 21.0),
        states=FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor", age_minutes=11),
                "sensor.outdoor": state(-5.0, "sensor.outdoor"),
            }
        ),
        engine=ControlEngine(),
        output=output,
    )

    result = asyncio.run(instance.async_update(NOW))

    assert result.supervised.fallback_active is True
    assert result.supervised.apply_physical is True
    assert output.outputs == [result.supervised]


def test_output_failure_enters_shadow_failsafe_and_resets_comfort_state() -> None:
    output = ActiveOutput(fail=True)
    instance = PumpSteerRuntime(
        config=RuntimeConfig("sensor.indoor", "sensor.outdoor", 21.0),
        states=FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor"),
                "sensor.outdoor": state(-5.0, "sensor.outdoor"),
            }
        ),
        engine=ControlEngine(),
        output=output,
    )

    result = asyncio.run(instance.async_update(NOW))

    assert result.error == "RuntimeError: simulated output failure"
    assert result.supervised.decision.state is ControlState.FAILSAFE
    assert result.supervised.fallback_active is True
    assert result.supervised.apply_physical is False
    assert result.engine_result.next_state.comfort.integral == 0


def test_runtime_shutdown_delegates_to_output_adapter() -> None:
    output = ActiveOutput()
    instance = PumpSteerRuntime(
        config=RuntimeConfig("sensor.indoor", "sensor.outdoor", 21.0),
        states=FakeStates({}),
        engine=ControlEngine(),
        output=output,
    )

    asyncio.run(instance.async_shutdown())

    assert output.shutdown_count == 1


def test_target_update_reaches_injected_engine() -> None:
    engine = FakeEngine()
    instance = runtime(
        FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor"),
                "sensor.outdoor": state(0.0, "sensor.outdoor"),
            }
        ),
        engine,
    )
    instance.set_target_temperature(22.5)

    asyncio.run(instance.async_update(NOW))

    assert instance.config.target_temperature == 22.5
    assert engine.targets == [22.5]


def test_saving_level_changes_only_economic_intent() -> None:
    instance = runtime(FakeStates({}), FakeEngine())

    instance.set_saving_level(4)

    assert instance.config.saving_level == 4
    assert instance.output.publish_count == 0
    with pytest.raises(ValueError, match="between 0 and 5"):
        instance.set_saving_level(6)


def test_stale_indoor_sensor_publishes_active_shadow_fallback() -> None:
    instance = runtime(
        FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor", age_minutes=11),
                "sensor.outdoor": state(-4.0, "sensor.outdoor"),
            }
        )
    )

    result = asyncio.run(instance.async_update(NOW))

    assert result.error is None
    assert result.supervised.fallback_active
    assert result.supervised.value == -4.0
    assert not result.supervised.apply_physical


def test_invalid_indoor_keeps_valid_outdoor_passthrough() -> None:
    instance = runtime(
        FakeStates(
            {
                "sensor.indoor": state(float("nan"), "sensor.indoor"),
                "sensor.outdoor": state(-7.0, "sensor.outdoor"),
            }
        )
    )

    result = asyncio.run(instance.async_update(NOW))

    assert result.error is not None
    assert result.supervised.fallback_active
    assert result.supervised.value == -7.0
    assert not result.supervised.apply_physical


def test_runtime_owns_engine_state_and_elapsed_time() -> None:
    engine = FakeEngine()
    instance = runtime(
        FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor"),
                "sensor.outdoor": state(-6.0, "sensor.outdoor"),
            }
        ),
        engine,
    )

    first = asyncio.run(instance.async_update(NOW))
    second = asyncio.run(instance.async_update(NOW + timedelta(seconds=90)))

    assert first.engine_result.next_state is not second.engine_result.next_state
    assert engine.dts == [timedelta(minutes=1), timedelta(seconds=90)]


def test_engine_exception_still_publishes_shadow_failsafe() -> None:
    output = NullOutput()
    instance = PumpSteerRuntime(
        config=RuntimeConfig("sensor.indoor", "sensor.outdoor", 21.0),
        states=FakeStates(
            {
                "sensor.indoor": state(20.0, "sensor.indoor"),
                "sensor.outdoor": state(-8.0, "sensor.outdoor"),
            }
        ),
        engine=FailingEngine(),
        output=output,
    )

    result = asyncio.run(instance.async_update(NOW))

    assert result.error == "RuntimeError: simulated engine failure"
    assert result.supervised.decision.state is ControlState.FAILSAFE
    assert result.supervised.value == -8.0
    assert not result.supervised.apply_physical
    assert output.latest is result.supervised


def test_runtime_config_rejects_invalid_target() -> None:
    with pytest.raises(ValueError, match="finite"):
        RuntimeConfig("sensor.indoor", "sensor.outdoor", float("nan"))
