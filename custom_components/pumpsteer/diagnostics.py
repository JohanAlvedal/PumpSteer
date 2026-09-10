"""Diagnostics support for the PumpSteer V3 config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import INTEGRATION_VERSION, PumpSteerEntryData
from .v3.pricing import DEFAULT_SAVING_LEVEL, price_policy_for_saving_level

DIAGNOSTICS_SCHEMA_VERSION = 5
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
        "shadow_mode": not getattr(runtime, "physical_control_enabled", False),
        "sources": {
            "indoor_temperature": config.indoor_entity,
            "outdoor_temperature": config.outdoor_entity,
        },
        "target_temperature": config.target_temperature,
        "physical_output": _output_snapshot(runtime),
        "economy": _economy_snapshot(
            getattr(config, "saving_level", DEFAULT_SAVING_LEVEL)
        ),
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


def _economy_snapshot(saving_level: object) -> dict[str, Any]:
    """Expose derived classification intent with no implied authority."""
    policy = price_policy_for_saving_level(saving_level)
    return {
        "mode": "shadow_only",
        "saving_level": policy.saving_level,
        "price_classification_requested": policy.classification_enabled,
        "cheap_percentile": policy.cheap_percentile,
        "expensive_percentile": policy.expensive_percentile,
        "price_planner_authority": False,
        "physical_control_authority": False,
    }


def _output_snapshot(runtime: Any) -> dict[str, Any]:
    """Expose physical-output state without MQTT credentials or payload history."""
    output = getattr(runtime, "output", None)
    snapshot = getattr(output, "snapshot", None)
    if snapshot is None:
        return {
            "mode": "disabled",
            "state": "shadow",
            "physical_control_enabled": False,
            "attempted_at": None,
            "commanded_temperature": None,
            "publish_count": getattr(output, "publish_count", 0),
            "last_error": None,
        }
    return {
        "mode": "ohmon_mqtt",
        "state": _enum_value(snapshot.state),
        "physical_control_enabled": bool(
            getattr(runtime, "physical_control_enabled", False)
        ),
        "attempted_at": _optional_timestamp(snapshot.attempted_at),
        "commanded_temperature": snapshot.commanded_temperature,
        "publish_count": snapshot.publish_count,
        "last_error": _safe_error(snapshot.last_error),
    }


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
            "thermal_evidence": _thermal_evidence_snapshot(None),
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
        "thermal_evidence": _thermal_evidence_snapshot(
            snapshot.thermal_evidence,
        ),
        "error": _safe_error(snapshot.last_error),
    }


def _thermal_evidence_snapshot(summary: Any | None) -> dict[str, Any]:
    """Expose counts and duration, never source values or inferred physics."""
    if summary is None:
        return {
            "scope": "latest_committed_batch",
            "maximum_claim": "descriptive_only",
            "interval_count": 0,
            "observed_duration_seconds": 0.0,
            "trend_counts": {
                "rising_observed": 0,
                "falling_observed": 0,
                "stable_observed": 0,
            },
            "skip_counts": {
                "no_indoor_progress": 0,
            },
            "optional_sensor_interval_counts": {
                "virtual_output": 0,
                "heating_power": 0,
                "supply": 0,
            },
            "physical_parameters_identifiable": False,
            "control_authority": False,
        }
    return {
        "scope": "latest_committed_batch",
        "maximum_claim": "descriptive_only",
        "interval_count": summary.interval_count,
        "observed_duration_seconds": summary.observed_duration_seconds,
        "trend_counts": {
            "rising_observed": summary.rising_interval_count,
            "falling_observed": summary.falling_interval_count,
            "stable_observed": summary.stable_interval_count,
        },
        "skip_counts": {
            "no_indoor_progress": summary.skipped_no_indoor_progress,
        },
        "optional_sensor_interval_counts": {
            "virtual_output": summary.virtual_output_interval_count,
            "heating_power": summary.heating_power_interval_count,
            "supply": summary.supply_temperature_interval_count,
        },
        "physical_parameters_identifiable": False,
        "control_authority": False,
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
