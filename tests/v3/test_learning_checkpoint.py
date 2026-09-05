"""Tests for the strict observation-learning checkpoint and checksum codec."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3.learning.checkpoint import (
    LEARNING_CHECKPOINT_SCHEMA_VERSION,
    LEARNING_PIPELINE_VERSION,
    MAX_TARGET_EPOCHS,
    LearningCheckpoint,
    TargetEpoch,
)
from custom_components.pumpsteer.v3.learning.checkpoint_codec import (
    decode_learning_checkpoint,
    encode_learning_checkpoint,
)
from custom_components.pumpsteer.v3.learning.episodes import EpisodeBoundary
from custom_components.pumpsteer.v3.learning.models import (
    AcceptedSample,
    RawTimelineBoundary,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
INDOOR = "sensor.indoor"
OUTDOOR = "sensor.outdoor"


def accepted(minute: int = -5, *, target: float = 21.0) -> AcceptedSample:
    captured = NOW + timedelta(minutes=minute)
    return AcceptedSample(
        captured_at=captured,
        indoor_temperature_c=20.5,
        outdoor_temperature_c=-5.0,
        target_temperature_c=target,
        indoor_observed_at=captured,
        outdoor_observed_at=captured - timedelta(minutes=1),
        virtual_output_c=-7.0,
        virtual_output_observed_at=captured,
        heating_power_kw=2.0,
        heating_power_observed_at=captured,
        supply_temperature_c=35.0,
        supply_temperature_observed_at=captured,
    )


def checkpoint() -> LearningCheckpoint:
    sample = accepted()
    return LearningCheckpoint(
        schema_version=LEARNING_CHECKPOINT_SCHEMA_VERSION,
        pipeline_version=LEARNING_PIPELINE_VERSION,
        entry_id="entry-1",
        saved_at=NOW + timedelta(minutes=2),
        indoor_entity_id=INDOOR,
        outdoor_entity_id=OUTDOOR,
        cursor_at=NOW,
        target_timeline=(
            TargetEpoch(NOW - timedelta(days=1), 21.0),
            TargetEpoch(NOW + timedelta(minutes=1), 22.0),
        ),
        boundary=EpisodeBoundary(
            previous_raw=RawTimelineBoundary(
                sample.captured_at,
                sample.indoor_observed_at,
                sample.outdoor_observed_at,
            ),
            previous_accepted=sample,
            open_episode_started_at=NOW - timedelta(hours=1),
            open_episode_sample_count=12,
        ),
    )


def decode(data, *, not_after=NOW + timedelta(minutes=2), **overrides):
    expected = {
        "expected_entry_id": "entry-1",
        "expected_indoor_entity_id": INDOOR,
        "expected_outdoor_entity_id": OUTDOOR,
        "not_after": not_after,
    }
    expected.update(overrides)
    return decode_learning_checkpoint(data, **expected)


def test_roundtrip_is_lossless_deterministic_and_json_safe() -> None:
    original = checkpoint()
    first = encode_learning_checkpoint(original)
    restored = decode(first)

    assert restored == original
    assert encode_learning_checkpoint(restored) == first
    assert len(first["checksum"]) == 64
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_checksum_detects_tampering() -> None:
    encoded = encode_learning_checkpoint(checkpoint())
    encoded["cursor_at"] = "2026-09-04T11:59:00Z"

    with pytest.raises(ValueError, match="checksum mismatch"):
        decode(encoded)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda data: data.pop("entry_id"), "invalid fields"),
        (lambda data: data.update({"unexpected": True}), "invalid fields"),
        (
            lambda data: data.update(
                {"schema_version": LEARNING_CHECKPOINT_SCHEMA_VERSION + 1}
            ),
            "future schema_version",
        ),
        (lambda data: data.update({"schema_version": 0}), "old schema_version"),
    ],
)
def test_missing_extra_future_and_old_schema_are_rejected(mutation, match) -> None:
    encoded = encode_learning_checkpoint(checkpoint())
    mutation(encoded)

    with pytest.raises(ValueError, match=match):
        decode(encoded)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"expected_entry_id": "other"}, "entry_id"),
        ({"expected_indoor_entity_id": "sensor.replacement"}, "indoor_entity_id"),
        ({"expected_outdoor_entity_id": "sensor.replacement"}, "outdoor_entity_id"),
    ],
)
def test_active_identity_must_match_exactly(override, match) -> None:
    with pytest.raises(ValueError, match=match):
        decode(encode_learning_checkpoint(checkpoint()), **override)


def test_future_checkpoint_is_rejected_against_injected_clock() -> None:
    with pytest.raises(ValueError, match="future"):
        decode(
            encode_learning_checkpoint(checkpoint()),
            not_after=NOW - timedelta(seconds=1),
        )


def test_timestamp_encoding_requires_canonical_z_suffix() -> None:
    encoded = encode_learning_checkpoint(checkpoint())
    encoded["saved_at"] = "2026-09-04T12:02:00+00:00"
    unsigned = {key: value for key, value in encoded.items() if key != "checksum"}
    encoded["checksum"] = hashlib.sha256(
        json.dumps(
            unsigned,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()

    with pytest.raises(ValueError, match="ISO 8601 UTC"):
        decode(encoded)


def test_noncanonical_number_is_rejected_before_object_construction() -> None:
    encoded = encode_learning_checkpoint(checkpoint())
    encoded["target_timeline"][0]["target_temperature_c"] = float("nan")

    with pytest.raises(ValueError, match="canonical JSON"):
        decode(encoded)


def test_target_timeline_is_bounded_and_strictly_ordered() -> None:
    common = {
        "schema_version": LEARNING_CHECKPOINT_SCHEMA_VERSION,
        "pipeline_version": LEARNING_PIPELINE_VERSION,
        "entry_id": "entry-1",
        "saved_at": NOW,
        "indoor_entity_id": INDOOR,
        "outdoor_entity_id": OUTDOOR,
        "cursor_at": NOW,
    }
    with pytest.raises(ValueError, match="strictly ordered"):
        LearningCheckpoint(
            **common,
            target_timeline=(TargetEpoch(NOW, 21.0), TargetEpoch(NOW, 22.0)),
        )
    with pytest.raises(ValueError, match="between 1 and 256"):
        LearningCheckpoint(
            **common,
            target_timeline=tuple(
                TargetEpoch(NOW - timedelta(minutes=index), 21.0)
                for index in range(MAX_TARGET_EPOCHS + 1, 0, -1)
            ),
        )


def test_boundary_must_precede_cursor_and_stay_inside_active_epoch() -> None:
    original = checkpoint()
    boundary = original.boundary

    with pytest.raises(ValueError, match="precede cursor"):
        LearningCheckpoint(
            **{
                field.name: getattr(original, field.name)
                for field in fields(LearningCheckpoint)
                if field.name != "boundary"
            },
            boundary=EpisodeBoundary(
                previous_raw=RawTimelineBoundary(NOW, NOW, NOW),
            ),
        )
    with pytest.raises(ValueError, match="active target epoch"):
        LearningCheckpoint(
            schema_version=original.schema_version,
            pipeline_version=original.pipeline_version,
            entry_id=original.entry_id,
            saved_at=original.saved_at,
            indoor_entity_id=original.indoor_entity_id,
            outdoor_entity_id=original.outdoor_entity_id,
            cursor_at=original.cursor_at,
            target_timeline=(TargetEpoch(NOW - timedelta(minutes=2), 21.0),),
            boundary=boundary,
        )


def test_checkpoint_has_no_model_confidence_or_control_authority() -> None:
    names = {field.name for field in fields(LearningCheckpoint)}

    assert {
        "model",
        "confidence",
        "authority",
        "control",
        "engine_state",
        "apply_physical",
        "cumulative_evidence",
    }.isdisjoint(names)
