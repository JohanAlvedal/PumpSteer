"""Independent query and merge scenarios for the V3 Recorder adapter."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from homeassistant.components import recorder as recorder_component


if not hasattr(recorder_component, "get_instance"):
    recorder_component.get_instance = lambda _hass: None

from custom_components.pumpsteer.v3.ha import recorder as recorder_adapter


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
INDOOR = "sensor.indoor"
OUTDOOR = "sensor.outdoor"


def _state(value, minute: int, *, unit: str = "°C"):
    observed = NOW + timedelta(minutes=minute)
    return SimpleNamespace(
        state=value,
        last_changed=observed,
        last_updated=observed,
        last_reported=observed,
        attributes={"unit_of_measurement": unit, "ignored": "secret"},
    )


def _assert_raises(error_type, function, *args, **kwargs) -> None:
    try:
        function(*args, **kwargs)
    except error_type:
        return
    raise AssertionError(f"Expected {error_type.__name__}")


def test_query_uses_recorder_instance_executor_and_exact_entity_allowlist() -> None:
    captured = {}
    hass = object()

    class Instance:
        async def async_add_executor_job(self, job):
            captured["executor_job"] = job
            return job()

    def get_instance(instance_hass):
        captured["instance_hass"] = instance_hass
        return Instance()

    def query(*args, **kwargs):
        captured["query_args"] = args
        captured["query_kwargs"] = kwargs
        return {
            INDOOR: [_state("20.0", 0)],
            OUTDOOR: [_state("-5.0", 0)],
        }

    old_instance = recorder_adapter.get_instance
    old_query = recorder_adapter.history.get_significant_states
    recorder_adapter.get_instance = get_instance
    recorder_adapter.history.get_significant_states = query
    try:
        result = asyncio.run(
            recorder_adapter.RecorderHistoryAdapter(hass).async_load(
                start=NOW,
                end=NOW + timedelta(hours=1),
                indoor_entity=INDOOR,
                outdoor_entity=OUTDOOR,
                target_temperature=21.0,
            )
        )
    finally:
        recorder_adapter.get_instance = old_instance
        recorder_adapter.history.get_significant_states = old_query

    assert len(result) == 1
    assert captured["instance_hass"] is hass
    assert captured["query_args"] == (hass, NOW, NOW + timedelta(hours=1))
    assert captured["query_kwargs"]["entity_ids"] == [INDOOR, OUTDOOR]
    assert set(captured["query_kwargs"]) == {
        "entity_ids",
        "include_start_time_state",
        "significant_changes_only",
        "minimal_response",
    }


def test_request_requires_bounded_utc_window_before_query() -> None:
    adapter = recorder_adapter.RecorderHistoryAdapter(object())

    _assert_raises(
        ValueError,
        asyncio.run,
        adapter.async_load(
            start=NOW.replace(tzinfo=None),
            end=NOW + timedelta(hours=1),
            indoor_entity=INDOOR,
            outdoor_entity=OUTDOOR,
            target_temperature=21.0,
        ),
    )
    _assert_raises(
        ValueError,
        asyncio.run,
        adapter.async_load(
            start=NOW,
            end=NOW + recorder_adapter.MAX_LOOKBACK + timedelta(seconds=1),
            indoor_entity=INDOOR,
            outdoor_entity=OUTDOOR,
            target_temperature=21.0,
        ),
    )


def test_union_timeline_preserves_true_source_report_timestamps() -> None:
    histories = {
        INDOOR: [_state("20.0", 0), _state("20.2", 10)],
        OUTDOOR: [_state("-5.0", 0), _state("-4.8", 5)],
    }

    samples = recorder_adapter.merge_histories(
        histories,
        indoor_entity=INDOOR,
        outdoor_entity=OUTDOOR,
        target_temperature=21.0,
    )

    assert [sample.captured_at for sample in samples] == [
        NOW,
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=10),
    ]
    assert samples[1].indoor_observed_at == NOW
    assert samples[1].outdoor_observed_at == NOW + timedelta(minutes=5)
    assert samples[2].indoor_observed_at == NOW + timedelta(minutes=10)
    assert samples[2].outdoor_observed_at == NOW + timedelta(minutes=5)


def test_merge_is_deterministic_and_enforces_sample_cap() -> None:
    histories = {
        INDOOR: [_state("20.0", 0), _state("20.2", 10)],
        OUTDOOR: [_state("-5.0", 0), _state("-4.8", 5)],
    }
    kwargs = {
        "indoor_entity": INDOOR,
        "outdoor_entity": OUTDOOR,
        "target_temperature": 21.0,
    }

    assert recorder_adapter.merge_histories(histories, **kwargs) == (
        recorder_adapter.merge_histories(histories, **kwargs)
    )
    _assert_raises(
        ValueError,
        recorder_adapter.merge_histories,
        histories,
        maximum_samples=2,
        **kwargs,
    )


def test_adapter_exports_observations_without_control_or_write_authority() -> None:
    samples = recorder_adapter.merge_histories(
        {INDOOR: [_state("20", 0)], OUTDOOR: [_state("-5", 0)]},
        indoor_entity=INDOOR,
        outdoor_entity=OUTDOOR,
        target_temperature=21.0,
    )
    fields = set(samples[0].__dataclass_fields__)

    assert "heating_request" not in fields
    assert "curtailment" not in fields
    assert "apply_physical" not in fields
    assert not hasattr(recorder_adapter.RecorderHistoryAdapter, "async_write")
    assert not hasattr(recorder_adapter.RecorderHistoryAdapter, "estimate")
