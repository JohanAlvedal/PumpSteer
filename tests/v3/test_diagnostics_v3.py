"""Tests for deterministic PumpSteer V3 config-entry diagnostics."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

from custom_components.pumpsteer.diagnostics import (
    DIAGNOSTICS_SCHEMA_VERSION,
    async_get_config_entry_diagnostics,
)
from custom_components.pumpsteer.v3 import (
    ControlDecision,
    ControlState,
    Observation,
    ReasonCode,
    SensorReading,
    Unit,
)
from custom_components.pumpsteer.v3.control.supervisor import (
    OutputConstraint,
    SupervisedOutput,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def entry_with_latest(latest) -> SimpleNamespace:
    runtime = SimpleNamespace(
        config=SimpleNamespace(
            indoor_entity="sensor.indoor",
            outdoor_entity="sensor.outdoor",
            target_temperature=21.5,
        ),
        latest=latest,
    )
    return SimpleNamespace(
        version=3,
        minor_version=0,
        runtime_data=SimpleNamespace(runtime=runtime),
    )


def test_diagnostics_handles_runtime_without_latest_result() -> None:
    result = asyncio.run(
        async_get_config_entry_diagnostics(None, entry_with_latest(None))
    )

    assert result["diagnostics_schema_version"] == DIAGNOSTICS_SCHEMA_VERSION
    assert result["shadow_mode"] is True
    assert result["sources"] == {
        "indoor_temperature": "sensor.indoor",
        "outdoor_temperature": "sensor.outdoor",
    }
    assert result["target_temperature"] == 21.5
    assert result["latest"] is None
    json.dumps(result)


def test_diagnostics_contains_only_defined_runtime_snapshot() -> None:
    indoor = SensorReading(20.5, NOW, Unit.CELSIUS, "sensor.indoor")
    outdoor = SensorReading(-4.0, NOW, Unit.CELSIUS, "sensor.outdoor")
    observation = Observation(NOW, indoor, outdoor)
    requested = ControlDecision.create(
        decided_at=NOW,
        state=ControlState.COMFORT,
        outdoor_temperature=-4.0,
        heating_request=2.0,
        reason_codes=[ReasonCode.COMFORT_BELOW_TARGET],
    )
    supervised_decision = ControlDecision.create(
        decided_at=NOW,
        state=ControlState.COMFORT,
        outdoor_temperature=-4.0,
        heating_request=1.5,
        reason_codes=[
            ReasonCode.COMFORT_BELOW_TARGET,
            ReasonCode.OUTPUT_RATE_LIMITED,
        ],
    )
    supervised = SupervisedOutput(
        decision=supervised_decision,
        apply_physical=False,
        constraints=(OutputConstraint.SLEW_LIMIT,),
    )
    latest = SimpleNamespace(
        observation=observation,
        requested=requested,
        supervised=supervised,
        error="ValueError: invalid input\nTraceback: secret details",
    )

    result = asyncio.run(
        async_get_config_entry_diagnostics(None, entry_with_latest(latest))
    )
    encoded = json.dumps(result)
    payload = result["latest"]

    assert payload["observation"]["indoor"]["value"] == 20.5
    assert payload["requested"]["virtual_temperature"] == -6.0
    assert payload["supervised"]["virtual_temperature"] == -5.5
    assert payload["supervised"]["apply_physical"] is False
    assert payload["supervised"]["constraints"] == ["slew_limit"]
    assert payload["supervised"]["state"] == "comfort"
    assert payload["supervised"]["reason_codes"] == [
        "comfort_below_target",
        "output_rate_limited",
    ]
    assert payload["error"] == "ValueError: invalid input"
    assert "Traceback" not in encoded
    assert "attributes" not in encoded
