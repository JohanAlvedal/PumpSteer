"""Regression tests for graceful loss of optional V3 optimization inputs."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3 import (
    ComfortPolicy,
    ControlState,
    Observation,
    SafetyPolicy,
    SensorReading,
    Unit,
)
from custom_components.pumpsteer.v3.control.engine import ControlEngine, EngineState


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def _temperature(value: float, source: str, *, observed_at: datetime = NOW) -> SensorReading:
    """Create one temperature reading for a deterministic control cycle."""
    return SensorReading(value, observed_at, Unit.CELSIUS, source)


def _price(value: float, *, observed_at: datetime = NOW) -> SensorReading:
    """Create one optional electricity-price reading."""
    return SensorReading(value, observed_at, Unit.SEK_PER_KWH, "price.test")


def _observation(
    *,
    include_price: bool,
    include_forecast: bool,
    optional_observed_at: datetime = NOW,
) -> Observation:
    """Build an observation with independently optional price and weather data."""
    return Observation(
        captured_at=NOW,
        indoor=_temperature(20.0, "indoor.test"),
        outdoor=_temperature(-5.0, "outdoor.test"),
        electricity_price=(
            _price(1.25, observed_at=optional_observed_at)
            if include_price
            else None
        ),
        forecast_outdoor=(
            (_temperature(-6.0, "weather.test", observed_at=optional_observed_at),)
            if include_forecast
            else ()
        ),
    )


def _run(observation: Observation):
    """Run one comfort cycle with no planner authority."""
    return ControlEngine().step(
        observation=observation,
        comfort_policy=ComfortPolicy(),
        safety_policy=SafetyPolicy(),
        state=EngineState(),
        now_utc=NOW,
        dt=timedelta(minutes=1),
    )


@pytest.mark.parametrize(
    ("include_price", "include_forecast"),
    (
        (False, False),
        (False, True),
        (True, False),
    ),
)
def test_missing_optional_inputs_never_trigger_failsafe(
    include_price: bool,
    include_forecast: bool,
) -> None:
    """Missing price/weather may reduce optimization, never comfort authority."""
    result = _run(
        _observation(
            include_price=include_price,
            include_forecast=include_forecast,
        )
    )

    assert result.requested_decision is not None
    assert result.comfort_result is not None
    assert result.supervised_output.decision.state is not ControlState.FAILSAFE
    assert not result.supervised_output.fallback_active


def test_stale_optional_inputs_never_trigger_failsafe() -> None:
    """Stale optional data cannot make otherwise healthy comfort control fail safe."""
    result = _run(
        _observation(
            include_price=True,
            include_forecast=True,
            optional_observed_at=NOW - timedelta(days=1),
        )
    )

    assert result.requested_decision is not None
    assert result.comfort_result is not None
    assert result.supervised_output.decision.state is not ControlState.FAILSAFE
    assert not result.supervised_output.fallback_active
