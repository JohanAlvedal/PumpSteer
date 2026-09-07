"""Tests for strictly descriptive thermal-evidence extraction."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3.learning import (
    AcceptedSample,
    EpisodeBatch,
    LearningEpisode,
    ThermalEvidencePolicy,
    ThermalTrend,
    extract_thermal_evidence,
)

START = datetime(2026, 1, 15, tzinfo=UTC)


def accepted(
    minute: float,
    *,
    indoor: float = 20.0,
    outdoor: float = -5.0,
    target: float = 21.0,
    indoor_minute: float | None = None,
    power: float | None = None,
) -> AcceptedSample:
    captured = START + timedelta(minutes=minute)
    indoor_at = START + timedelta(
        minutes=minute if indoor_minute is None else indoor_minute
    )
    return AcceptedSample(
        captured_at=captured,
        indoor_temperature_c=indoor,
        outdoor_temperature_c=outdoor,
        target_temperature_c=target,
        indoor_observed_at=indoor_at,
        outdoor_observed_at=captured,
        heating_power_kw=power,
        heating_power_observed_at=captured if power is not None else None,
    )


def batch(
    *episodes: tuple[AcceptedSample, ...], continues: bool = False
) -> EpisodeBatch:
    return EpisodeBatch(
        episodes=tuple(LearningEpisode(samples=item) for item in episodes),
        excluded=(),
        first_episode_continues=continues,
    )


def test_observed_trends_use_elapsed_time_and_not_pump_assumptions() -> None:
    result = extract_thermal_evidence(
        batch(
            (
                accepted(0, indoor=20.0),
                accepted(10, indoor=20.1),
                accepted(20, indoor=20.0),
                accepted(30, indoor=20.01),
            )
        )
    )

    assert [item.trend for item in result.intervals] == [
        ThermalTrend.RISING_OBSERVED,
        ThermalTrend.FALLING_OBSERVED,
        ThermalTrend.STABLE_OBSERVED,
    ]
    assert result.intervals[0].indoor_rate_c_per_hour == pytest.approx(0.6)
    assert result.summary.observed_duration_seconds == 30 * 60
    assert result.summary.interval_count == 3
    assert result.summary.heating_power_interval_count == 0


def test_outdoor_only_union_rows_do_not_create_pseudo_response() -> None:
    result = extract_thermal_evidence(
        batch(
            (
                accepted(0, indoor=20.0),
                accepted(5, indoor=20.0, outdoor=-6.0, indoor_minute=0),
                accepted(10, indoor=20.1, outdoor=-6.0),
            )
        )
    )

    assert result.summary.interval_count == 1
    assert result.summary.skipped_no_indoor_progress == 1
    assert result.intervals[0].duration_seconds == 10 * 60
    assert result.intervals[0].indoor_rate_c_per_hour == pytest.approx(0.6)
    assert result.intervals[0].mean_indoor_outdoor_delta_c == pytest.approx(26.05)


def test_continued_episode_accounts_for_cross_batch_edge_once() -> None:
    previous = accepted(0, indoor=20.0)
    result = extract_thermal_evidence(
        batch((accepted(10, indoor=20.1), accepted(20, indoor=20.2)), continues=True),
        previous_accepted=previous,
    )

    assert result.summary.interval_count == 2
    assert [item.crosses_batch_boundary for item in result.intervals] == [True, False]


def test_outdoor_only_row_does_not_hide_cross_batch_interval() -> None:
    previous = accepted(0, indoor=20.0)
    result = extract_thermal_evidence(
        batch(
            (
                accepted(5, indoor=20.0, outdoor=-6.0, indoor_minute=0),
                accepted(10, indoor=20.1, outdoor=-6.0),
            ),
            continues=True,
        ),
        previous_accepted=previous,
    )

    assert result.intervals[0].duration_seconds == 10 * 60


def test_split_batch_summary_matches_uninterrupted_extraction() -> None:
    first = accepted(0, indoor=20.0, outdoor=-5.0)
    outdoor_only = accepted(
        5,
        indoor=20.0,
        outdoor=-6.0,
        indoor_minute=0,
        power=2.0,
    )
    current = accepted(10, indoor=20.1, outdoor=-6.0, power=3.0)

    uninterrupted = extract_thermal_evidence(batch((first, outdoor_only, current)))
    before_restart = extract_thermal_evidence(batch((first, outdoor_only)))
    after_restart = extract_thermal_evidence(
        batch((current,), continues=True),
        previous_accepted=outdoor_only,
    )

    assert uninterrupted.summary == before_restart.summary.merged(after_restart.summary)
    assert uninterrupted.intervals == (
        replace(after_restart.intervals[0], crosses_batch_boundary=False),
    )


def test_separate_episodes_are_never_bridged() -> None:
    result = extract_thermal_evidence(
        batch(
            (accepted(0), accepted(10, indoor=20.1)),
            (accepted(20, indoor=19.0), accepted(30, indoor=19.1)),
        )
    )

    assert result.summary.interval_count == 2


def test_dense_valid_updates_form_evidence_instead_of_permanent_warmup() -> None:
    result = extract_thermal_evidence(
        batch(tuple(accepted(i, indoor=20.0 + i * 0.01) for i in range(11)))
    )

    assert result.summary.interval_count == 10
    assert result.summary.observed_duration_seconds == 10 * 60


@pytest.mark.parametrize(
    "samples",
    [
        (accepted(10), accepted(5)),
        (accepted(0), accepted(10, indoor_minute=-1)),
    ],
)
def test_invalid_timeline_is_rejected_not_silently_repaired(samples) -> None:
    with pytest.raises(ValueError):
        extract_thermal_evidence(batch(samples))


def test_target_change_is_rejected_defensively() -> None:
    with pytest.raises(ValueError, match="target change"):
        extract_thermal_evidence(
            batch((accepted(0, target=21.0), accepted(10, target=22.0)))
        )


def test_optional_pump_data_is_coverage_only() -> None:
    without = extract_thermal_evidence(batch((accepted(0), accepted(10, indoor=20.1))))
    with_power = extract_thermal_evidence(
        batch(
            (
                accepted(0, power=2.0),
                accepted(10, indoor=20.1, power=3.0),
            )
        )
    )

    assert (
        without.intervals[0].indoor_rate_c_per_hour
        == with_power.intervals[0].indoor_rate_c_per_hour
    )
    assert without.summary.heating_power_interval_count == 0
    assert with_power.summary.heating_power_interval_count == 1


def test_public_result_has_no_model_or_control_authority_fields() -> None:
    names = {
        item.name
        for result_type in (type(extract_thermal_evidence(batch()).summary),)
        for item in fields(result_type)
    }

    assert not names & {
        "confidence",
        "heat_loss",
        "thermal_capacitance",
        "cop",
        "brake_duration",
        "control_authority",
    }


def test_policy_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError):
        ThermalEvidencePolicy(minimum_resolvable_change_c=-0.1)
