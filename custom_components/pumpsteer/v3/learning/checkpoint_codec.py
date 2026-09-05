"""Strict deterministic codec for observation-learning checkpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from ..validation import finite_float
from .checkpoint import (
    LEARNING_CHECKPOINT_SCHEMA_VERSION,
    LEARNING_PIPELINE_VERSION,
    LearningCheckpoint,
    TargetEpoch,
)
from .episodes import EpisodeBoundary
from .models import AcceptedSample, RawTimelineBoundary

_ROOT_FIELDS = {
    "schema_version",
    "pipeline_version",
    "entry_id",
    "saved_at",
    "source_identity",
    "cursor_at",
    "target_timeline",
    "boundary",
    "checksum",
}
_SOURCE_FIELDS = {"indoor_entity_id", "outdoor_entity_id"}
_EPOCH_FIELDS = {"started_at", "target_temperature_c"}
_BOUNDARY_FIELDS = {
    "previous_raw",
    "previous_accepted",
    "open_episode_started_at",
    "open_episode_sample_count",
}
_RAW_FIELDS = {"captured_at", "indoor_observed_at", "outdoor_observed_at"}
_ACCEPTED_FIELDS = {
    "captured_at",
    "indoor_temperature_c",
    "outdoor_temperature_c",
    "target_temperature_c",
    "indoor_observed_at",
    "outdoor_observed_at",
    "virtual_output_c",
    "virtual_output_observed_at",
    "heating_power_kw",
    "heating_power_observed_at",
    "supply_temperature_c",
    "supply_temperature_observed_at",
}


def encode_learning_checkpoint(checkpoint: LearningCheckpoint) -> dict[str, Any]:
    """Encode a validated checkpoint and attach its canonical SHA-256 checksum."""
    if not isinstance(checkpoint, LearningCheckpoint):
        raise TypeError("checkpoint must be a LearningCheckpoint")
    payload: dict[str, Any] = {
        "schema_version": checkpoint.schema_version,
        "pipeline_version": checkpoint.pipeline_version,
        "entry_id": checkpoint.entry_id,
        "saved_at": _format_timestamp(checkpoint.saved_at),
        "source_identity": {
            "indoor_entity_id": checkpoint.indoor_entity_id,
            "outdoor_entity_id": checkpoint.outdoor_entity_id,
        },
        "cursor_at": _format_timestamp(checkpoint.cursor_at),
        "target_timeline": [
            {
                "started_at": _format_timestamp(epoch.started_at),
                "target_temperature_c": epoch.target_temperature_c,
            }
            for epoch in checkpoint.target_timeline
        ],
        "boundary": _encode_boundary(checkpoint.boundary),
    }
    payload["checksum"] = _checksum(payload)
    return payload


def decode_learning_checkpoint(
    data: Mapping[str, Any],
    *,
    expected_entry_id: str,
    expected_indoor_entity_id: str,
    expected_outdoor_entity_id: str,
    not_after: datetime,
) -> LearningCheckpoint:
    """Strictly validate identity, time, schema and checksum before restoration."""
    root = _exact_mapping(data, _ROOT_FIELDS, "checkpoint")
    schema_version = root["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise TypeError("schema_version must be an integer")
    if schema_version > LEARNING_CHECKPOINT_SCHEMA_VERSION:
        raise ValueError(f"unsupported future schema_version: {schema_version}")
    if schema_version < LEARNING_CHECKPOINT_SCHEMA_VERSION:
        raise ValueError(f"unsupported old schema_version: {schema_version}")
    if root["pipeline_version"] != LEARNING_PIPELINE_VERSION:
        raise ValueError("pipeline_version does not match the running pipeline")

    supplied_checksum = root["checksum"]
    if (
        not isinstance(supplied_checksum, str)
        or len(supplied_checksum) != 64
        or any(character not in "0123456789abcdef" for character in supplied_checksum)
    ):
        raise ValueError("checksum must be a lowercase SHA-256 digest")
    unsigned = dict(root)
    del unsigned["checksum"]
    if not hmac.compare_digest(supplied_checksum, _checksum(unsigned)):
        raise ValueError("checkpoint checksum mismatch")

    entry_id = _expected_string(root["entry_id"], expected_entry_id, "entry_id")
    source = _exact_mapping(root["source_identity"], _SOURCE_FIELDS, "source_identity")
    indoor = _expected_string(
        source["indoor_entity_id"],
        expected_indoor_entity_id,
        "indoor_entity_id",
    )
    outdoor = _expected_string(
        source["outdoor_entity_id"],
        expected_outdoor_entity_id,
        "outdoor_entity_id",
    )
    not_after = _utc_datetime(not_after, "not_after")
    saved_at = _parse_timestamp(root["saved_at"], "saved_at")
    if saved_at > not_after:
        raise ValueError("saved_at cannot be in the future")

    timeline_value = root["target_timeline"]
    if not isinstance(timeline_value, list):
        raise TypeError("target_timeline must be a list")
    timeline = tuple(
        TargetEpoch(
            started_at=_parse_timestamp(
                epoch["started_at"], f"target_timeline[{index}].started_at"
            ),
            target_temperature_c=finite_float(
                epoch["target_temperature_c"],
                f"target_timeline[{index}].target_temperature_c",
            ),
        )
        for index, item in enumerate(timeline_value)
        for epoch in (_exact_mapping(item, _EPOCH_FIELDS, f"target_timeline[{index}]"),)
    )
    checkpoint = LearningCheckpoint(
        schema_version=schema_version,
        pipeline_version=root["pipeline_version"],
        entry_id=entry_id,
        saved_at=saved_at,
        indoor_entity_id=indoor,
        outdoor_entity_id=outdoor,
        cursor_at=_parse_timestamp(root["cursor_at"], "cursor_at"),
        target_timeline=timeline,
        boundary=_decode_boundary(root["boundary"]),
    )
    if any(epoch.started_at > not_after for epoch in checkpoint.target_timeline):
        raise ValueError("target epoch cannot be in the future")
    return checkpoint


def _encode_boundary(boundary: EpisodeBoundary) -> dict[str, Any]:
    raw = boundary.previous_raw
    accepted = boundary.previous_accepted
    return {
        "previous_raw": None
        if raw is None
        else {
            "captured_at": _format_timestamp(raw.captured_at),
            "indoor_observed_at": _format_optional_timestamp(raw.indoor_observed_at),
            "outdoor_observed_at": _format_optional_timestamp(raw.outdoor_observed_at),
        },
        "previous_accepted": None
        if accepted is None
        else {
            "captured_at": _format_timestamp(accepted.captured_at),
            "indoor_temperature_c": accepted.indoor_temperature_c,
            "outdoor_temperature_c": accepted.outdoor_temperature_c,
            "target_temperature_c": accepted.target_temperature_c,
            "indoor_observed_at": _format_timestamp(accepted.indoor_observed_at),
            "outdoor_observed_at": _format_timestamp(accepted.outdoor_observed_at),
            "virtual_output_c": accepted.virtual_output_c,
            "virtual_output_observed_at": _format_optional_timestamp(
                accepted.virtual_output_observed_at
            ),
            "heating_power_kw": accepted.heating_power_kw,
            "heating_power_observed_at": _format_optional_timestamp(
                accepted.heating_power_observed_at
            ),
            "supply_temperature_c": accepted.supply_temperature_c,
            "supply_temperature_observed_at": _format_optional_timestamp(
                accepted.supply_temperature_observed_at
            ),
        },
        "open_episode_started_at": _format_optional_timestamp(
            boundary.open_episode_started_at
        ),
        "open_episode_sample_count": boundary.open_episode_sample_count,
    }


def _decode_boundary(value: Any) -> EpisodeBoundary:
    data = _exact_mapping(value, _BOUNDARY_FIELDS, "boundary")
    raw_data = data["previous_raw"]
    raw = None
    if raw_data is not None:
        raw_mapping = _exact_mapping(raw_data, _RAW_FIELDS, "boundary.previous_raw")
        raw = RawTimelineBoundary(
            captured_at=_parse_timestamp(
                raw_mapping["captured_at"], "boundary.previous_raw.captured_at"
            ),
            indoor_observed_at=_parse_optional_timestamp(
                raw_mapping["indoor_observed_at"],
                "boundary.previous_raw.indoor_observed_at",
            ),
            outdoor_observed_at=_parse_optional_timestamp(
                raw_mapping["outdoor_observed_at"],
                "boundary.previous_raw.outdoor_observed_at",
            ),
        )
    accepted_data = data["previous_accepted"]
    accepted = None
    if accepted_data is not None:
        accepted_mapping = _exact_mapping(
            accepted_data, _ACCEPTED_FIELDS, "boundary.previous_accepted"
        )
        accepted = AcceptedSample(
            captured_at=_parse_timestamp(
                accepted_mapping["captured_at"],
                "boundary.previous_accepted.captured_at",
            ),
            indoor_temperature_c=finite_float(
                accepted_mapping["indoor_temperature_c"], "indoor_temperature_c"
            ),
            outdoor_temperature_c=finite_float(
                accepted_mapping["outdoor_temperature_c"], "outdoor_temperature_c"
            ),
            target_temperature_c=finite_float(
                accepted_mapping["target_temperature_c"], "target_temperature_c"
            ),
            indoor_observed_at=_parse_timestamp(
                accepted_mapping["indoor_observed_at"], "indoor_observed_at"
            ),
            outdoor_observed_at=_parse_timestamp(
                accepted_mapping["outdoor_observed_at"], "outdoor_observed_at"
            ),
            virtual_output_c=_optional_float(
                accepted_mapping["virtual_output_c"], "virtual_output_c"
            ),
            virtual_output_observed_at=_parse_optional_timestamp(
                accepted_mapping["virtual_output_observed_at"],
                "virtual_output_observed_at",
            ),
            heating_power_kw=_optional_float(
                accepted_mapping["heating_power_kw"], "heating_power_kw"
            ),
            heating_power_observed_at=_parse_optional_timestamp(
                accepted_mapping["heating_power_observed_at"],
                "heating_power_observed_at",
            ),
            supply_temperature_c=_optional_float(
                accepted_mapping["supply_temperature_c"], "supply_temperature_c"
            ),
            supply_temperature_observed_at=_parse_optional_timestamp(
                accepted_mapping["supply_temperature_observed_at"],
                "supply_temperature_observed_at",
            ),
        )
    return EpisodeBoundary(
        previous_raw=raw,
        previous_accepted=accepted,
        open_episode_started_at=_parse_optional_timestamp(
            data["open_episode_started_at"], "boundary.open_episode_started_at"
        ),
        open_episode_sample_count=_integer(
            data["open_episode_sample_count"], "boundary.open_episode_sample_count"
        ),
    )


def _exact_mapping(value: Any, fields: set[str], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        extra = sorted(actual - fields)
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if extra:
            details.append("extra: " + ", ".join(extra))
        raise ValueError(f"{field_name} has invalid fields ({'; '.join(details)})")
    return value


def _checksum(payload: Mapping[str, Any]) -> str:
    try:
        canonical = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as err:
        raise ValueError("checkpoint is not canonical JSON") from err
    return hashlib.sha256(canonical).hexdigest()


def _expected_string(value: Any, expected: str, field_name: str) -> str:
    if not isinstance(expected, str) or not expected.strip():
        raise ValueError(f"expected_{field_name} must be a non-empty string")
    if not isinstance(value, str) or value != expected:
        raise ValueError(f"checkpoint {field_name} does not match the active entry")
    return value


def _integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _optional_float(value: Any, field_name: str) -> float | None:
    return None if value is None else finite_float(value, field_name)


def _format_optional_timestamp(value: datetime | None) -> str | None:
    return None if value is None else _format_timestamp(value)


def _format_timestamp(value: datetime) -> str:
    value = _utc_datetime(value, "timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_optional_timestamp(value: Any, field_name: str) -> datetime | None:
    return None if value is None else _parse_timestamp(value, field_name)


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be an ISO 8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise ValueError(f"{field_name} must be an ISO 8601 UTC timestamp") from err
    return _utc_datetime(parsed, field_name)


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value.astimezone(UTC)
