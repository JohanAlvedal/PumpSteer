"""Tests for the versioned PumpSteer V3 checkpoint codec."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3 import ControlDecision, ControlState, ReasonCode
from custom_components.pumpsteer.v3.control.comfort_controller import (
    ComfortControllerState,
)
from custom_components.pumpsteer.v3.control.engine import EngineState
from custom_components.pumpsteer.v3.control.supervisor import (
    OutputConstraint,
    SupervisedOutput,
)
from custom_components.pumpsteer.v3.storage import (
    CURRENT_SCHEMA_VERSION,
    PersistedState,
    decode_persisted_state,
    encode_persisted_state,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def checkpoint() -> PersistedState:
    decision = ControlDecision.create(
        decided_at=NOW - timedelta(minutes=1),
        state=ControlState.COMFORT,
        outdoor_temperature=-5.0,
        heating_request=2.5,
        reason_codes=(ReasonCode.COMFORT_BELOW_TARGET,),
    )
    output = SupervisedOutput(
        decision=decision,
        apply_physical=True,
        constraints=(OutputConstraint.QUANTIZED,),
    )
    return PersistedState(
        schema_version=CURRENT_SCHEMA_VERSION,
        algorithm_version="3.0.0-dev1",
        saved_at=NOW,
        target_temperature=21.0,
        preset="balanced",
        engine_state=EngineState(
            comfort=ComfortControllerState(
                integral=1.25,
                last_step_at=NOW - timedelta(minutes=1),
            ),
            previous_output=output,
            last_indoor_observed_at=NOW - timedelta(seconds=30),
            last_outdoor_observed_at=NOW - timedelta(seconds=45),
        ),
    )


def test_roundtrip_is_lossless_and_deterministic() -> None:
    original = checkpoint()
    first_encoding = encode_persisted_state(original)
    restored = decode_persisted_state(first_encoding)

    assert restored == original
    assert encode_persisted_state(restored) == first_encoding
    assert first_encoding["saved_at"] == "2026-01-15T12:00:00Z"


def test_encoding_contains_only_json_compatible_values() -> None:
    import json

    encoded = encode_persisted_state(checkpoint())

    assert json.loads(json.dumps(encoded, allow_nan=False)) == encoded


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_are_rejected(value: float) -> None:
    encoded = encode_persisted_state(checkpoint())
    encoded["target_temperature"] = value

    with pytest.raises(ValueError, match="finite"):
        decode_persisted_state(encoded)


def test_naive_timestamp_is_rejected() -> None:
    encoded = encode_persisted_state(checkpoint())
    encoded["saved_at"] = "2026-01-15T12:00:00"

    with pytest.raises(ValueError, match="timezone-aware"):
        decode_persisted_state(encoded)


def test_non_utc_timestamp_is_rejected() -> None:
    encoded = encode_persisted_state(checkpoint())
    encoded["saved_at"] = "2026-01-15T13:00:00+01:00"

    with pytest.raises(ValueError, match="must use UTC"):
        decode_persisted_state(encoded)


def test_unknown_future_schema_is_rejected() -> None:
    encoded = encode_persisted_state(checkpoint())
    encoded["schema_version"] = CURRENT_SCHEMA_VERSION + 1

    with pytest.raises(ValueError, match="future schema_version"):
        decode_persisted_state(encoded)


def test_incompatible_algorithm_version_is_rejected() -> None:
    encoded = encode_persisted_state(checkpoint())

    with pytest.raises(ValueError, match="does not match"):
        decode_persisted_state(
            encoded,
            expected_algorithm_version="3.0.0-dev2",
        )


@pytest.mark.parametrize("target", [4.5, 35.5])
def test_target_outside_supported_range_is_rejected(target: float) -> None:
    encoded = encode_persisted_state(checkpoint())
    encoded["target_temperature"] = target

    with pytest.raises(ValueError, match="between 5 and 35"):
        decode_persisted_state(encoded)


def test_corrupt_nested_output_is_rejected() -> None:
    encoded = encode_persisted_state(checkpoint())
    encoded["engine_state"]["previous_output"]["decision"]["heating_request"] = "bad"

    with pytest.raises(ValueError, match="invalid previous_output"):
        decode_persisted_state(encoded)


def test_missing_required_field_is_rejected() -> None:
    encoded = encode_persisted_state(checkpoint())
    del encoded["engine_state"]

    with pytest.raises(ValueError, match="missing required field"):
        decode_persisted_state(encoded)


def test_explicit_schema_zero_migrates_to_current_schema() -> None:
    legacy = {
        "schema_version": 0,
        "algorithm_version": "3.0.0-alpha",
        "saved_at": "2026-01-15T12:00:00Z",
        "target_temperature": 20.5,
        "preset": "comfort",
        "integral": 0.75,
        "last_step_at": "2026-01-15T11:59:00Z",
    }

    restored = decode_persisted_state(legacy)

    assert restored.schema_version == CURRENT_SCHEMA_VERSION
    assert restored.engine_state.comfort.integral == 0.75
    assert restored.engine_state.previous_output is None


def test_missing_schema_version_uses_documented_legacy_migration() -> None:
    legacy = {
        "algorithm_version": "3.0.0-alpha",
        "saved_at": "2026-01-15T12:00:00Z",
        "target_temperature": 21.0,
        "preset": "balanced",
        "integral": 0.0,
    }

    assert decode_persisted_state(legacy).schema_version == CURRENT_SCHEMA_VERSION


def test_bare_learned_parameter_is_not_a_supported_checkpoint() -> None:
    with pytest.raises(ValueError, match="legacy schema 0 is missing"):
        decode_persisted_state({"thermal_k": 0.05})


def test_persisted_state_is_immutable() -> None:
    state = checkpoint()

    with pytest.raises(AttributeError):
        state.target_temperature = 22.0


def test_real_engine_sensor_timestamps_survive_restart() -> None:
    original = checkpoint()

    restored = decode_persisted_state(encode_persisted_state(original))

    assert restored.engine_state.last_indoor_observed_at == (
        original.engine_state.last_indoor_observed_at
    )
    assert restored.engine_state.last_outdoor_observed_at == (
        original.engine_state.last_outdoor_observed_at
    )


def test_engine_sensor_timestamp_cannot_be_later_than_checkpoint() -> None:
    with pytest.raises(ValueError, match="cannot be later than saved_at"):
        PersistedState(
            schema_version=CURRENT_SCHEMA_VERSION,
            algorithm_version="3.0.0-dev1",
            saved_at=NOW,
            target_temperature=21.0,
            preset="balanced",
            engine_state=EngineState(
                last_indoor_observed_at=NOW + timedelta(seconds=1)
            ),
        )


def test_controller_step_timestamp_cannot_be_later_than_checkpoint() -> None:
    with pytest.raises(ValueError, match="cannot be later than saved_at"):
        PersistedState(
            schema_version=CURRENT_SCHEMA_VERSION,
            algorithm_version="3.0.0-dev1",
            saved_at=NOW,
            target_temperature=21.0,
            preset="balanced",
            engine_state=EngineState(
                comfort=ComfortControllerState(last_step_at=NOW + timedelta(seconds=1))
            ),
        )
