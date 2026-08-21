"""Diagnostics support for the PumpSteer V3 config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import INTEGRATION_VERSION, PumpSteerEntryData

DIAGNOSTICS_SCHEMA_VERSION = 2
_MAX_ERROR_LENGTH = 240


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return a deterministic and JSON-serializable V3 runtime snapshot."""
    del hass
    data: PumpSteerEntryData = entry.runtime_data
    runtime = data.runtime
    config = runtime.config
    latest = runtime.latest

    snapshot: dict[str, Any] = {
        "integration_version": INTEGRATION_VERSION,
        "config_entry_version": getattr(entry, "version", 3),
        "config_entry_minor_version": getattr(entry, "minor_version", 0),
        "diagnostics_schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "shadow_mode": True,
        "sources": {
            "indoor_temperature": config.indoor_entity,
            "outdoor_temperature": config.outdoor_entity,
        },
        "target_temperature": config.target_temperature,
        "learning": _learning_snapshot(
            getattr(data, "learning_runtime", None),
        ),
        "latest": None,
    }
    if latest is None:
        return snapshot

    requested = latest.requested
    supervised = latest.supervised
    snapshot["latest"] = {
        "observation": _observation_snapshot(latest.observation),
        "requested": _decision_snapshot(requested),
        "supervised": {
            **_decision_snapshot(supervised.decision),
            "apply_physical": bool(supervised.apply_physical),
            "fallback_active": bool(supervised.fallback_active),
            "constraints": [
                _enum_value(constraint) for constraint in supervised.constraints
            ],
        },
        "error": _safe_error(latest.error),
    }
    return snapshot


def _observation_snapshot(observation: Any | None) -> dict[str, Any] | None:
    if observation is None:
        return None
    return {
        "captured_at": observation.captured_at.isoformat(),
        "indoor": {
            "value": observation.indoor.value,
            "observed_at": observation.indoor.observed_at.isoformat(),
            "unit": _enum_value(observation.indoor.unit),
        },
        "outdoor": {
            "value": observation.outdoor.value,
            "observed_at": observation.outdoor.observed_at.isoformat(),
            "unit": _enum_value(observation.outdoor.unit),
        },
    }


def _decision_snapshot(decision: Any | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "decided_at": decision.decided_at.isoformat(),
        "state": _enum_value(decision.state),
        "outdoor_temperature": decision.outdoor_temperature,
        "heating_request": decision.heating_request,
        "curtailment": decision.curtailment,
        "virtual_temperature": decision.virtual_temperature,
        "reason_codes": [_enum_value(reason) for reason in decision.reason_codes],
    }


def _learning_snapshot(runtime: Any | None) -> dict[str, Any]:
    """Expose aggregate observation metadata without Recorder sample values."""
    if runtime is None:
        return {
            "mode": "observation_only",
            "stage": "observing",
            "status": "unavailable",
            "target_epoch_started_at": None,
            "cursor_at": None,
            "attempted_at": None,
            "window_start": None,
            "window_end": None,
            "raw_sample_count": 0,
            "accepted_sample_count": 0,
            "episode_count": 0,
            "excluded_sample_count": 0,
            "exclusion_counts": {},
            "error": None,
        }
    snapshot = runtime.snapshot
    return {
        "mode": "observation_only",
        "stage": _enum_value(snapshot.stage),
        "status": _enum_value(snapshot.status),
        "target_epoch_started_at": snapshot.target_epoch_started_at.isoformat(),
        "cursor_at": snapshot.cursor_at.isoformat(),
        "attempted_at": _optional_timestamp(snapshot.attempted_at),
        "window_start": _optional_timestamp(snapshot.window_start),
        "window_end": _optional_timestamp(snapshot.window_end),
        "raw_sample_count": snapshot.raw_sample_count,
        "accepted_sample_count": snapshot.accepted_sample_count,
        "episode_count": snapshot.episode_count,
        "excluded_sample_count": snapshot.excluded_sample_count,
        "exclusion_counts": dict(snapshot.exclusion_counts),
        "error": _safe_error(snapshot.last_error),
    }


def _optional_timestamp(value: Any | None) -> str | None:
    return None if value is None else value.isoformat()


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _safe_error(error: Any | None) -> str | None:
    """Return one bounded line and discard traceback-shaped continuation data."""
    if error is None:
        return None
    first_line = str(error).splitlines()[0].strip()
    return first_line[:_MAX_ERROR_LENGTH]
