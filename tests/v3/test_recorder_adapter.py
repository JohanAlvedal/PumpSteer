"""Tests for the read-only PumpSteer Recorder history adapter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.components import recorder as recorder_component
from homeassistant.components.recorder import history


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
CAPTURED: dict = {}


class RecorderInstance:
    async def async_add_executor_job(self, job):
        CAPTURED["job"] = job
        return job()


def get_instance(hass):
    CAPTURED["instance_hass"] = hass
    return RecorderInstance()


def get_significant_states(*args, **kwargs):
    CAPTURED["query_args"] = args
    CAPTURED["query_kwargs"] = kwargs
    return CAPTURED["history"]


recorder_component.get_instance = get_instance
history.get_significant_states = get_significant_states

from custom_components.pumpsteer.v3.ha.recorder import (  # noqa: E402
    MAX_LOOKBACK,
    RecorderHistoryAdapter,
    merge_histories,
)
from custom_components.pumpsteer.v3.ha import recorder as recorder_adapter  # noqa: E402
from custom_components.pumpsteer.v3.learning.episodes import (  # noqa: E402
    segment_episodes,
)
from custom_components.pumpsteer.v3.learning.models import (  # noqa: E402
    RawRecorderSample,
)

recorder_adapter.get_instance = get_instance


def state(
    value,
    changed_minutes: int,
    *,
    updated_minutes: int | None = None,
    reported_minutes: int | None = None,
    unit: str = "°C",
):
    changed = NOW + timedelta(minutes=changed_minutes)
    updated = NOW + timedelta(
        minutes=changed_minutes if updated_minutes is None else updated_minutes
    )
    result = SimpleNamespace(
        state=value,
        last_changed=changed,
        last_updated=updated,
        attributes={"unit_of_measurement": unit, "ignored": "secret"},
    )
    if reported_minutes is not None:
        result.last_reported = NOW + timedelta(minutes=reported_minutes)
    return result


def test_executor_query_uses_required_recorder_flags() -> None:
    hass = object()
    CAPTURED.clear()
    CAPTURED["history"] = {
        "sensor.indoor": [state("20.0", 0)],
        "sensor.outdoor": [state("-5.0", 0)],
    }

    result = asyncio.run(
        RecorderHistoryAdapter(hass).async_load(
            start=NOW,
            end=NOW + timedelta(hours=1),
            indoor_entity="sensor.indoor",
            outdoor_entity="sensor.outdoor",
            target_temperature=21.0,
        )
    )

    assert len(result) == 1
    assert CAPTURED["instance_hass"] is hass
    assert CAPTURED["query_args"] == (hass, NOW, NOW + timedelta(hours=1))
    assert CAPTURED["query_kwargs"] == {
        "entity_ids": ["sensor.indoor", "sensor.outdoor"],
        "include_start_time_state": True,
        "significant_changes_only": False,
        "minimal_response": False,
    }


def test_executor_result_is_clamped_to_requested_half_open_window() -> None:
    CAPTURED.clear()
    CAPTURED["history"] = {
        "sensor.indoor": [
            state("19.9", -30),
            state("20.0", 10),
            state("20.1", 60),
        ],
        "sensor.outdoor": [state("-5.0", -30), state("-4.9", 20)],
    }

    result = asyncio.run(
        RecorderHistoryAdapter(object()).async_load(
            start=NOW,
            end=NOW + timedelta(hours=1),
            indoor_entity="sensor.indoor",
            outdoor_entity="sensor.outdoor",
            target_temperature=21.0,
        )
    )

    assert [sample.captured_at for sample in result] == [
        NOW + timedelta(minutes=10),
        NOW + timedelta(minutes=20),
    ]
    assert result[0].outdoor_observed_at == NOW - timedelta(minutes=30)


def test_merge_uses_union_timestamps_and_preserves_observed_at() -> None:
    histories = {
        "sensor.indoor": [state("20.0", 0), state("20.5", 10, updated_minutes=11)],
        "sensor.outdoor": [state("-5.0", 5), state("-4.0", 15)],
    }

    samples = merge_histories(
        histories,
        indoor_entity="sensor.indoor",
        outdoor_entity="sensor.outdoor",
        target_temperature=21.5,
    )

    assert [sample.captured_at for sample in samples] == [
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=11),
        NOW + timedelta(minutes=15),
    ]
    assert [
        (sample.indoor_temperature_c, sample.outdoor_temperature_c)
        for sample in samples
    ] == [
        (20.0, -5.0),
        (20.5, -5.0),
        (20.5, -4.0),
    ]
    assert samples[1].indoor_observed_at == NOW + timedelta(minutes=11)
    assert all(sample.target_temperature_c == 21.5 for sample in samples)


def test_missing_source_returns_no_samples() -> None:
    assert (
        merge_histories(
            {"sensor.indoor": [state("20", 0)]},
            indoor_entity="sensor.indoor",
            outdoor_entity="sensor.outdoor",
            target_temperature=21.0,
        )
        == ()
    )


def test_bad_states_and_unsupported_units_are_marked_not_estimated() -> None:
    samples = merge_histories(
        {
            "sensor.indoor": [state("unavailable", 0)],
            "sensor.outdoor": [state("50", 0, unit="°F")],
        },
        indoor_entity="sensor.indoor",
        outdoor_entity="sensor.outdoor",
        target_temperature=21.0,
    )

    assert samples[0].indoor_temperature_c is None
    assert samples[0].outdoor_temperature_c is None


def test_report_time_orders_attribute_only_history_rows() -> None:
    histories = {
        "sensor.indoor": [
            state("20.0", 0, updated_minutes=0, reported_minutes=0),
            state("20.1", 0, updated_minutes=9, reported_minutes=10),
        ],
        "sensor.outdoor": [state("-5.0", 0, reported_minutes=5)],
    }

    samples = merge_histories(
        histories,
        indoor_entity="sensor.indoor",
        outdoor_entity="sensor.outdoor",
        target_temperature=21.0,
    )

    assert [sample.captured_at for sample in samples] == [
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=10),
    ]
    assert samples[1].indoor_observed_at == NOW + timedelta(minutes=10)
    assert samples[1].indoor_observed_at <= samples[1].captured_at


def test_canonical_samples_feed_episode_segmentation_without_translation() -> None:
    samples = merge_histories(
        {
            "sensor.indoor": [state("20.0", 0), state("20.1", 10)],
            "sensor.outdoor": [state("-5.0", 0), state("-4.9", 5)],
        },
        indoor_entity="sensor.indoor",
        outdoor_entity="sensor.outdoor",
        target_temperature=21.0,
    )

    assert all(isinstance(sample, RawRecorderSample) for sample in samples)
    batch = segment_episodes(samples)
    assert len(batch.episodes) == 1
    assert len(batch.episodes[0].samples) == len(samples)
    assert batch.excluded == ()


def test_bounds_and_sample_cap_are_enforced_before_processing() -> None:
    adapter = RecorderHistoryAdapter(object())
    with pytest.raises(ValueError, match="lookback"):
        asyncio.run(
            adapter.async_load(
                start=NOW,
                end=NOW + MAX_LOOKBACK + timedelta(seconds=1),
                indoor_entity="sensor.indoor",
                outdoor_entity="sensor.outdoor",
                target_temperature=21.0,
            )
        )
    with pytest.raises(ValueError, match="sample cap"):
        merge_histories(
            {
                "sensor.indoor": [state("20", index) for index in range(3)],
                "sensor.outdoor": [state("0", 0)],
            },
            indoor_entity="sensor.indoor",
            outdoor_entity="sensor.outdoor",
            target_temperature=21.0,
            maximum_samples=1,
        )
