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
from custom_components.pumpsteer.v3.enums import LearningStage
from custom_components.pumpsteer.v3.ha.learning_runtime import (
    LearningRuntimeStatus,
    LearningSnapshot,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def entry_with_latest(
    latest, learning_runtime=None, *, saving_level: int = 3
) -> SimpleNamespace:
    runtime = SimpleNamespace(
        config=SimpleNamespace(
            indoor_entity="sensor.indoor",
            outdoor_entity="sensor.outdoor",
            target_temperature=21.5,
            saving_level=saving_level,
        ),
        latest=latest,
    )
    return SimpleNamespace(
        version=3,
        minor_version=0,
        runtime_data=SimpleNamespace(
            runtime=runtime,
            learning_runtime=learning_runtime,
        ),
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
    assert result["economy"] == {
        "mode": "shadow_only",
        "saving_level": 3,
        "price_classification_requested": True,
        "cheap_percentile": 30,
        "expensive_percentile": 80,
        "price_planner_authority": False,
        "physical_control_authority": False,
    }
    assert result["learning"]["mode"] == "observation_only"
    assert result["learning"]["status"] == "unavailable"
    assert result["latest"] is None
    json.dumps(result)


def test_diagnostics_maps_changed_and_disabled_saving_levels() -> None:
    maximum = asyncio.run(
        async_get_config_entry_diagnostics(
            None,
            entry_with_latest(None, saving_level=5),
        )
    )["economy"]
    disabled = asyncio.run(
        async_get_config_entry_diagnostics(
            None,
            entry_with_latest(None, saving_level=0),
        )
    )["economy"]

    assert (maximum["cheap_percentile"], maximum["expensive_percentile"]) == (
        40,
        60,
    )
    assert maximum["price_planner_authority"] is False
    assert disabled["price_classification_requested"] is False
    assert disabled["cheap_percentile"] is None
    assert disabled["expensive_percentile"] is None


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


def test_diagnostics_exposes_only_aggregate_learning_snapshot() -> None:
    learning = SimpleNamespace(
        snapshot=LearningSnapshot(
            stage=LearningStage.OBSERVING,
            status=LearningRuntimeStatus.ERROR,
            target_epoch_started_at=NOW,
            cursor_at=NOW,
            attempted_at=NOW,
            window_start=NOW,
            window_end=NOW,
            raw_sample_count=7,
            accepted_sample_count=4,
            episode_count=2,
            excluded_sample_count=3,
            exclusion_counts=(("stale_source", 3),),
            last_error="collection_failed:RuntimeError",
        )
    )

    result = asyncio.run(
        async_get_config_entry_diagnostics(
            None,
            entry_with_latest(None, learning),
        )
    )
    snapshot = result["learning"]
    encoded = json.dumps(snapshot)

    assert snapshot["stage"] == "observing"
    assert snapshot["status"] == "error"
    assert snapshot["accepted_sample_count"] == 4
    assert snapshot["exclusion_counts"] == {"stale_source": 3}
    assert snapshot["thermal_evidence"] == {
        "scope": "latest_committed_batch",
        "maximum_claim": "descriptive_only",
        "interval_count": 0,
        "observed_duration_seconds": 0.0,
        "trend_counts": {
            "rising_observed": 0,
            "falling_observed": 0,
            "stable_observed": 0,
        },
        "skip_counts": {"no_indoor_progress": 0},
        "optional_sensor_interval_counts": {
            "virtual_output": 0,
            "heating_power": 0,
            "supply": 0,
        },
        "physical_parameters_identifiable": False,
        "control_authority": False,
    }
    assert snapshot["error"] == "collection_failed:RuntimeError"
    assert "temperature" not in encoded
    assert "Traceback" not in encoded
