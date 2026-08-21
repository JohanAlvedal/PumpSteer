"""JSON-compatible checkpoint codec without file-system responsibilities.

The future Home Assistant storage adapter owns atomic I/O: write a complete encoded
checkpoint to a temporary object, flush it, and atomically replace the committed
checkpoint. This codec only validates and transforms complete in-memory objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..control.comfort_controller import ComfortControllerState
from ..control.engine import EngineState
from ..control.supervisor import OutputConstraint, SupervisedOutput
from ..enums import ControlState, ReasonCode
from ..models import ControlDecision
from ..validation import finite_float
from .schema import CURRENT_SCHEMA_VERSION, PersistedState


def encode_persisted_state(state: PersistedState) -> dict[str, Any]:
    """Encode a checkpoint into deterministic JSON-compatible primitives."""
    if not isinstance(state, PersistedState):
        raise TypeError("state must be a PersistedState")
    engine = state.engine_state
    return {
        "schema_version": state.schema_version,
        "algorithm_version": state.algorithm_version,
        "saved_at": _format_timestamp(state.saved_at),
        "target_temperature": state.target_temperature,
        "preset": state.preset,
        "engine_state": {
            "comfort": {
                "integral": engine.comfort.integral,
                "last_step_at": _format_optional_timestamp(engine.comfort.last_step_at),
            },
            "previous_output": _encode_output(engine.previous_output),
            "last_indoor_observed_at": _format_optional_timestamp(
                engine.last_indoor_observed_at
            ),
            "last_outdoor_observed_at": _format_optional_timestamp(
                engine.last_outdoor_observed_at
            ),
        },
    }


def decode_persisted_state(
    data: Mapping[str, Any],
    *,
    expected_algorithm_version: str | None = None,
) -> PersistedState:
    """Validate, migrate, and decode a complete checkpoint.

    Schema 0 is the only supported legacy input. It is represented by a missing
    ``schema_version`` and stores comfort state at the top level. Unknown future
    schemas and all malformed values are rejected rather than partially restored.
    """
    if not isinstance(data, Mapping):
        raise TypeError("checkpoint must be a mapping")
    migrated = _migrate(dict(data))
    algorithm_version = _nonempty_string(
        migrated.get("algorithm_version"), "algorithm_version"
    )
    if (
        expected_algorithm_version is not None
        and algorithm_version != expected_algorithm_version
    ):
        raise ValueError(
            "checkpoint algorithm_version does not match the running algorithm"
        )
    try:
        engine_data = _mapping(migrated["engine_state"], "engine_state")
        comfort_data = _mapping(engine_data["comfort"], "engine_state.comfort")
        comfort = ComfortControllerState(
            integral=finite_float(comfort_data["integral"], "integral"),
            last_step_at=_parse_optional_timestamp(
                comfort_data.get("last_step_at"), "last_step_at"
            ),
        )
        engine = EngineState(
            comfort=comfort,
            previous_output=_decode_output(engine_data.get("previous_output")),
            last_indoor_observed_at=_parse_optional_timestamp(
                engine_data.get("last_indoor_observed_at"),
                "engine_state.last_indoor_observed_at",
            ),
            last_outdoor_observed_at=_parse_optional_timestamp(
                engine_data.get("last_outdoor_observed_at"),
                "engine_state.last_outdoor_observed_at",
            ),
        )
        return PersistedState(
            schema_version=CURRENT_SCHEMA_VERSION,
            algorithm_version=algorithm_version,
            saved_at=_parse_timestamp(migrated["saved_at"], "saved_at"),
            target_temperature=finite_float(
                migrated["target_temperature"], "target_temperature"
            ),
            preset=_nonempty_string(migrated["preset"], "preset"),
            engine_state=engine,
        )
    except KeyError as err:
        raise ValueError(
            f"checkpoint is missing required field: {err.args[0]}"
        ) from err


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    raw_version = data.get("schema_version")
    if raw_version is None:
        required = {
            "algorithm_version",
            "saved_at",
            "target_temperature",
            "preset",
            "integral",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(
                "legacy schema 0 is missing required fields: " + ", ".join(missing)
            )
        return {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "algorithm_version": data["algorithm_version"],
            "saved_at": data["saved_at"],
            "target_temperature": data["target_temperature"],
            "preset": data["preset"],
            "engine_state": {
                "comfort": {
                    "integral": data["integral"],
                    "last_step_at": data.get("last_step_at"),
                },
                "previous_output": None,
                "last_indoor_observed_at": data.get("last_indoor_observed_at"),
                "last_outdoor_observed_at": data.get("last_outdoor_observed_at"),
            },
        }
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise ValueError("schema_version must be an integer")
    if raw_version > CURRENT_SCHEMA_VERSION:
        raise ValueError(f"unsupported future schema_version: {raw_version}")
    if raw_version < 0:
        raise ValueError(f"unsupported schema_version: {raw_version}")
    if raw_version == 0:
        legacy = dict(data)
        legacy.pop("schema_version")
        return _migrate(legacy)
    return data


def _encode_output(output: SupervisedOutput | None) -> dict[str, Any] | None:
    if output is None:
        return None
    decision = output.decision
    return {
        "decision": {
            "decided_at": _format_timestamp(decision.decided_at),
            "state": decision.state.value,
            "outdoor_temperature": decision.outdoor_temperature,
            "heating_request": decision.heating_request,
            "curtailment": decision.curtailment,
            "reason_codes": [reason.value for reason in decision.reason_codes],
        },
        "apply_physical": output.apply_physical,
        "constraints": [constraint.value for constraint in output.constraints],
        "fallback_active": output.fallback_active,
    }


def _decode_output(value: Any) -> SupervisedOutput | None:
    if value is None:
        return None
    output = _mapping(value, "previous_output")
    decision_data = _mapping(output.get("decision"), "previous_output.decision")
    try:
        decision = ControlDecision.create(
            decided_at=_parse_timestamp(decision_data["decided_at"], "decided_at"),
            state=ControlState(decision_data["state"]),
            outdoor_temperature=finite_float(
                decision_data["outdoor_temperature"], "outdoor_temperature"
            ),
            heating_request=finite_float(
                decision_data["heating_request"], "heating_request"
            ),
            curtailment=finite_float(decision_data["curtailment"], "curtailment"),
            reason_codes=tuple(
                ReasonCode(reason) for reason in decision_data["reason_codes"]
            ),
        )
        apply_physical = _boolean(output["apply_physical"], "apply_physical")
        fallback_active = _boolean(output["fallback_active"], "fallback_active")
        constraints = tuple(
            OutputConstraint(item) for item in output.get("constraints", ())
        )
    except KeyError as err:
        raise ValueError(
            f"previous_output is missing required field: {err.args[0]}"
        ) from err
    except (TypeError, ValueError) as err:
        raise ValueError(f"invalid previous_output: {err}") from err
    return SupervisedOutput(
        decision=decision,
        apply_physical=apply_physical,
        constraints=constraints,
        fallback_active=fallback_active,
    )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _format_optional_timestamp(value: datetime | None) -> str | None:
    return None if value is None else _format_timestamp(value)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must use UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_optional_timestamp(value: Any, field_name: str) -> datetime | None:
    return None if value is None else _parse_timestamp(value, field_name)


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be an ISO 8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise ValueError(f"{field_name} must be an ISO 8601 UTC timestamp") from err
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must use UTC")
    return parsed.astimezone(UTC)
