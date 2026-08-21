"""Read-only Home Assistant Recorder history adapter for PumpSteer V3."""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant

from ..learning.models import RawRecorderSample

CELSIUS = "°C"
DEFAULT_MAX_SAMPLES = 10_000
HARD_MAX_SAMPLES = 50_000
MAX_LOOKBACK = timedelta(days=31)
MIN_TARGET_TEMPERATURE = 5.0
MAX_TARGET_TEMPERATURE = 35.0


class RecorderHistoryAdapter:
    """Load bounded Recorder history without interpreting data quality."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def async_load(
        self,
        *,
        start: datetime,
        end: datetime,
        indoor_entity: str,
        outdoor_entity: str,
        target_temperature: float,
        maximum_samples: int = DEFAULT_MAX_SAMPLES,
    ) -> tuple[RawRecorderSample, ...]:
        """Load and merge a bounded UTC interval through Recorder's executor."""
        start, end, target, cap = _validate_request(
            start,
            end,
            indoor_entity,
            outdoor_entity,
            target_temperature,
            maximum_samples,
        )
        query = functools.partial(
            history.get_significant_states,
            self._hass,
            start,
            end,
            entity_ids=[indoor_entity, outdoor_entity],
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
        )
        raw = await get_instance(self._hass).async_add_executor_job(query)
        return merge_histories(
            raw,
            indoor_entity=indoor_entity,
            outdoor_entity=outdoor_entity,
            target_temperature=target,
            maximum_samples=cap,
        )


def merge_histories(
    histories: dict[str, list[Any]],
    *,
    indoor_entity: str,
    outdoor_entity: str,
    target_temperature: float,
    maximum_samples: int = DEFAULT_MAX_SAMPLES,
) -> tuple[RawRecorderSample, ...]:
    """Merge two state histories using union timestamps and last-known state."""
    target = _validate_target(target_temperature)
    cap = _validate_cap(maximum_samples)
    indoor_states = list(histories.get(indoor_entity, ()))
    outdoor_states = list(histories.get(outdoor_entity, ()))
    if not indoor_states or not outdoor_states:
        return ()
    if len(indoor_states) + len(outdoor_states) > cap * 2:
        raise ValueError("Recorder history exceeds the configured sample cap")

    indoor_events = _ordered_events(indoor_states)
    outdoor_events = _ordered_events(outdoor_states)
    timestamps = sorted(
        {event.timestamp for event in (*indoor_events, *outdoor_events)}
    )
    if len(timestamps) > cap:
        raise ValueError("Merged Recorder history exceeds the configured sample cap")

    indoor_index = 0
    outdoor_index = 0
    indoor_current: _Event | None = None
    outdoor_current: _Event | None = None
    samples: list[RawRecorderSample] = []

    for timestamp in timestamps:
        while (
            indoor_index < len(indoor_events)
            and indoor_events[indoor_index].timestamp <= timestamp
        ):
            indoor_current = indoor_events[indoor_index]
            indoor_index += 1
        while (
            outdoor_index < len(outdoor_events)
            and outdoor_events[outdoor_index].timestamp <= timestamp
        ):
            outdoor_current = outdoor_events[outdoor_index]
            outdoor_index += 1
        if indoor_current is None or outdoor_current is None:
            continue
        samples.append(
            RawRecorderSample(
                captured_at=timestamp,
                indoor_temperature_c=indoor_current.value,
                outdoor_temperature_c=outdoor_current.value,
                target_temperature_c=target,
                indoor_observed_at=indoor_current.observed_at,
                outdoor_observed_at=outdoor_current.observed_at,
            )
        )
    return tuple(samples)


@dataclass(frozen=True, slots=True)
class _Event:
    timestamp: datetime
    observed_at: datetime
    value: float | None
    order: int


def _ordered_events(states: list[Any]) -> list[_Event]:
    events: list[_Event] = []
    for order, state in enumerate(states):
        report_time = getattr(state, "last_reported", None) or state.last_updated
        observed_at = _as_utc(report_time, "state report timestamp")
        unit_supported = state.attributes.get("unit_of_measurement") == CELSIUS
        events.append(
            _Event(
                timestamp=observed_at,
                observed_at=observed_at,
                value=_raw_float(state.state) if unit_supported else None,
                order=order,
            )
        )
    return sorted(
        events,
        key=lambda event: (event.timestamp, event.observed_at, event.order),
    )


def _raw_float(value: Any) -> float | None:
    if value in (None, "unknown", "unavailable", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_request(
    start: datetime,
    end: datetime,
    indoor_entity: str,
    outdoor_entity: str,
    target_temperature: float,
    maximum_samples: int,
) -> tuple[datetime, datetime, float, int]:
    start = _as_utc(start, "start")
    end = _as_utc(end, "end")
    if end <= start:
        raise ValueError("end must be later than start")
    if end - start > MAX_LOOKBACK:
        raise ValueError("Recorder lookback exceeds the maximum interval")
    for name, entity_id in (
        ("indoor_entity", indoor_entity),
        ("outdoor_entity", outdoor_entity),
    ):
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError(f"{name} must be a non-empty entity ID")
    if indoor_entity == outdoor_entity:
        raise ValueError("indoor and outdoor entities must be distinct")
    return (
        start,
        end,
        _validate_target(target_temperature),
        _validate_cap(maximum_samples),
    )


def _validate_target(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError("target_temperature must be numeric") from err
    if not math.isfinite(result):
        raise ValueError("target_temperature must be finite")
    if not MIN_TARGET_TEMPERATURE <= result <= MAX_TARGET_TEMPERATURE:
        raise ValueError("target_temperature must be between 5 and 35 °C")
    return result


def _validate_cap(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("maximum_samples must be an integer")
    if not 1 <= value <= HARD_MAX_SAMPLES:
        raise ValueError("maximum_samples is outside the supported range")
    return value


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value
