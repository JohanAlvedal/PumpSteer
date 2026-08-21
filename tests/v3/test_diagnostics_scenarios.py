"""Independent safety scenarios for PumpSteer V3 diagnostics."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from custom_components.pumpsteer.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.pumpsteer.v3.control.supervisor import (
    OutputConstraint,
    SupervisedOutput,
)
from custom_components.pumpsteer.v3.enums import ControlState, ReasonCode, Unit
from custom_components.pumpsteer.v3.models import (
    ControlDecision,
    Observation,
    SensorReading,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _entry(latest) -> SimpleNamespace:
    runtime = SimpleNamespace(
        config=SimpleNamespace(
            indoor_entity="sensor.indoor",
            outdoor_entity="sensor.outdoor",
            target_temperature=21.0,
        ),
        latest=latest,
    )
    return SimpleNamespace(
        version=3,
        minor_version=0,
        runtime_data=SimpleNamespace(runtime=runtime, learning_runtime=None),
    )


def _decision(*, reasons=(ReasonCode.COMFORT_BELOW_TARGET,)) -> ControlDecision:
    return ControlDecision.create(
        decided_at=NOW,
        state=ControlState.COMFORT,
        outdoor_temperature=-5.0,
        heating_request=2.0,
        reason_codes=reasons,
    )


def _latest(*, error=None, observation=None) -> SimpleNamespace:
    decision = _decision(
        reasons=(
            ReasonCode.COMFORT_BELOW_TARGET,
            ReasonCode.OUTPUT_RATE_LIMITED,
        )
    )
    supervised = SupervisedOutput(
        decision=decision,
        apply_physical=False,
        constraints=(OutputConstraint.SLEW_LIMIT,),
    )
    return SimpleNamespace(
        observation=observation,
        requested=_decision(),
        supervised=supervised,
        error=error,
        attributes={"password": "must-not-leak"},
        traceback="must-not-leak",
    )


def _diagnostics(entry) -> dict:
    return asyncio.run(async_get_config_entry_diagnostics(None, entry))


def test_empty_runtime_snapshot_is_json_serializable_and_shadow_only() -> None:
    result = _diagnostics(_entry(None))

    assert json.loads(json.dumps(result)) == result
    assert result["shadow_mode"] is True
    assert result["latest"] is None
    assert result["learning"]["mode"] == "observation_only"
    assert "apply_physical" not in result


def test_latest_snapshot_never_claims_physical_write() -> None:
    result = _diagnostics(_entry(_latest()))
    supervised = result["latest"]["supervised"]

    assert result["shadow_mode"] is True
    assert supervised["apply_physical"] is False
    assert "physical_write" not in json.dumps(result).lower()


def test_reason_and_constraint_values_are_stable_plain_strings() -> None:
    result = _diagnostics(_entry(_latest()))
    supervised = result["latest"]["supervised"]

    assert supervised["state"] == "comfort"
    assert supervised["reason_codes"] == [
        "comfort_below_target",
        "output_rate_limited",
    ]
    assert supervised["constraints"] == ["slew_limit"]
    assert all(type(value) is str for value in supervised["reason_codes"])
    assert all(type(value) is str for value in supervised["constraints"])


def test_error_is_bounded_to_one_line_without_traceback_continuation() -> None:
    long_first_line = "ValueError: " + "x" * 400
    error = long_first_line + "\nTraceback (most recent call last):\nsecret path"

    result = _diagnostics(_entry(_latest(error=error)))
    safe_error = result["latest"]["error"]

    assert safe_error is not None
    assert len(safe_error) <= 240
    assert "\n" not in safe_error
    assert "Traceback" not in safe_error
    assert "secret path" not in json.dumps(result)


def test_observation_does_not_copy_arbitrary_state_attributes_or_sources() -> None:
    indoor = SensorReading(20.0, NOW, Unit.CELSIUS, "private.indoor_source")
    outdoor = SensorReading(-5.0, NOW, Unit.CELSIUS, "private.outdoor_source")
    observation = Observation(NOW, indoor, outdoor)

    result = _diagnostics(_entry(_latest(observation=observation)))
    encoded = json.dumps(result)
    snapshot = result["latest"]["observation"]

    assert set(snapshot) == {"captured_at", "indoor", "outdoor"}
    assert set(snapshot["indoor"]) == {"value", "observed_at", "unit"}
    assert "private.indoor_source" not in encoded
    assert "password" not in encoded
    assert "must-not-leak" not in encoded
    assert "traceback" not in encoded.lower()


def test_latest_error_without_observation_remains_safe_and_serializable() -> None:
    latest = _latest(error="ValueError: indoor unavailable", observation=None)

    result = _diagnostics(_entry(latest))

    assert result["latest"]["observation"] is None
    assert result["latest"]["error"] == "ValueError: indoor unavailable"
    json.dumps(result, allow_nan=False)
