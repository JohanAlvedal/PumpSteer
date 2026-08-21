"""Shadow-runtime scenarios at the Home Assistant adapter boundary."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.pumpsteer.v3.control.engine import ControlEngine
from custom_components.pumpsteer.v3.enums import ControlState, ReasonCode, Unit
from custom_components.pumpsteer.v3.ha.runtime import (
    NullOutput,
    PumpSteerRuntime,
    RawState,
    RuntimeConfig,
)


START = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
INDOOR = "sensor.indoor"
OUTDOOR = "sensor.outdoor"


class FakeStates:
    """Mutable read-only state-provider fake used by runtime scenarios."""

    def __init__(self, values: dict[str, RawState]) -> None:
        self.values = values

    def get_state(self, entity_id: str) -> RawState | None:
        return self.values.get(entity_id)


def _raw(value: object, now: datetime, source: str) -> RawState:
    return RawState(value, now, Unit.CELSIUS, source)


def _runtime(
    *,
    indoor: object = 19.0,
    outdoor: object = -5.0,
    observed_at: datetime = START,
) -> tuple[PumpSteerRuntime, FakeStates, NullOutput]:
    states = FakeStates(
        {
            INDOOR: _raw(indoor, observed_at, INDOOR),
            OUTDOOR: _raw(outdoor, observed_at, OUTDOOR),
        }
    )
    output = NullOutput()
    runtime = PumpSteerRuntime(
        config=RuntimeConfig(INDOOR, OUTDOOR, target_temperature=21.0),
        states=states,
        engine=ControlEngine(),
        output=output,
    )
    return runtime, states, output


def test_valid_states_run_canonical_engine_in_shadow() -> None:
    async def scenario() -> None:
        runtime, _, output = _runtime()

        result = await runtime.async_update(START)

        assert result.error is None
        assert result.requested is not None
        assert result.requested.state is ControlState.COMFORT
        assert result.requested.heating_request > 0.0
        assert result.supervised.apply_physical is False
        assert output.latest is result.engine_result.supervised_output
        assert output.publish_count == 1

    asyncio.run(scenario())


def test_absent_optional_sources_do_not_block_comfort() -> None:
    async def scenario() -> None:
        runtime, states, _ = _runtime()
        assert set(states.values) == {INDOOR, OUTDOOR}

        result = await runtime.async_update(START)

        assert result.observation is not None
        assert result.observation.electricity_price is None
        assert result.observation.forecast_outdoor == ()
        assert result.engine_result.comfort_result is not None
        assert result.supervised.fallback_active is False

    asyncio.run(scenario())


def test_stale_indoor_enters_shadow_failsafe_with_outdoor_passthrough() -> None:
    async def scenario() -> None:
        stale = START - timedelta(minutes=11)
        runtime, states, output = _runtime(observed_at=stale)
        states.values[OUTDOOR] = _raw(-7.0, START, OUTDOOR)

        result = await runtime.async_update(START)

        assert result.error is None
        assert result.supervised.decision.state is ControlState.FAILSAFE
        assert result.supervised.value == -7.0
        assert result.supervised.apply_physical is False
        assert ReasonCode.STALE_SENSOR in result.engine_result.input_reasons
        assert output.publish_count == 1

    asyncio.run(scenario())


def test_nan_indoor_keeps_valid_outdoor_as_failsafe_passthrough() -> None:
    async def scenario() -> None:
        runtime, _, output = _runtime(indoor=float("nan"), outdoor=-8.0)

        result = await runtime.async_update(START)

        assert result.observation is None
        assert result.error is not None and "finite" in result.error
        assert result.supervised.decision.state is ControlState.FAILSAFE
        assert result.supervised.value == -8.0
        assert result.supervised.apply_physical is False
        assert output.latest is result.supervised

    asyncio.run(scenario())


def test_future_sensor_timestamp_enters_failsafe_and_passthrough() -> None:
    async def scenario() -> None:
        runtime, states, _ = _runtime()
        states.values[INDOOR] = _raw(19.0, START + timedelta(seconds=1), INDOOR)

        result = await runtime.async_update(START)

        assert result.error is None
        assert result.supervised.decision.state is ControlState.FAILSAFE
        assert result.supervised.value == -5.0
        assert ReasonCode.INDOOR_SENSOR_INVALID in result.engine_result.input_reasons

    asyncio.run(scenario())


def test_missing_indoor_still_publishes_shadow_passthrough() -> None:
    async def scenario() -> None:
        runtime, states, output = _runtime(outdoor=-6.0)
        states.values.pop(INDOOR)

        result = await runtime.async_update(START)

        assert result.error is not None and "missing" in result.error
        assert result.supervised.decision.state is ControlState.FAILSAFE
        assert result.supervised.value == -6.0
        assert result.supervised.apply_physical is False
        assert output.publish_count == 1

    asyncio.run(scenario())


def test_irregular_runtime_gap_is_bounded_by_engine() -> None:
    async def scenario() -> None:
        runtime, states, _ = _runtime(indoor=20.0)
        first = await runtime.async_update(START)
        later = START + timedelta(hours=3)
        states.values[INDOOR] = _raw(18.0, later, INDOOR)
        states.values[OUTDOOR] = _raw(-5.0, later, OUTDOOR)

        second = await runtime.async_update(later)

        comfort = second.engine_result.comfort_result
        assert comfort is not None and comfort.dt_bounded is True
        assert abs(second.supervised.value - first.supervised.value) <= 2.0
        assert second.supervised.apply_physical is False

    asyncio.run(scenario())


def test_target_update_changes_request_and_preserves_sources() -> None:
    async def scenario() -> None:
        runtime, states, _ = _runtime(indoor=20.0)
        runtime.set_target_temperature(20.0)
        first = await runtime.async_update(START)
        later = START + timedelta(minutes=1)
        states.values[INDOOR] = _raw(20.0, later, INDOOR)
        states.values[OUTDOOR] = _raw(-5.0, later, OUTDOOR)
        runtime.set_target_temperature(22.0)

        raised = await runtime.async_update(later)

        assert runtime.config.indoor_entity == INDOOR
        assert runtime.config.outdoor_entity == OUTDOOR
        assert first.requested is not None and raised.requested is not None
        assert raised.requested.heating_request > first.requested.heating_request
        assert runtime.output.publish_count == 2

    asyncio.run(scenario())


def test_runtime_replay_is_deterministic() -> None:
    async def replay() -> list:
        runtime, states, _ = _runtime()
        results = []
        now = START
        for indoor in (19.0, 19.5, 20.0, 20.5, 21.0):
            states.values[INDOOR] = _raw(indoor, now, INDOOR)
            states.values[OUTDOOR] = _raw(-5.0, now, OUTDOOR)
            results.append(await runtime.async_update(now))
            now += timedelta(minutes=1)
        return results

    assert asyncio.run(replay()) == asyncio.run(replay())
