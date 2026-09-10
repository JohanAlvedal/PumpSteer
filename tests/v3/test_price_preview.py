"""Contract tests for V3's authority-free price preview."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from custom_components.pumpsteer.v3 import (
    ComfortPolicy,
    Observation,
    SafetyPolicy,
    SensorReading,
    Unit,
)
from custom_components.pumpsteer.v3.control.engine import ControlEngine, EngineState
from custom_components.pumpsteer.v3.pricing import (
    PriceBand,
    PricePoint,
    PricePreviewReason,
    PricePreviewStatus,
    PriceThresholds,
    PriceTimeline,
    ShadowPricePlan,
    build_shadow_price_plan,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def timeline(
    prices: list[float],
    *,
    interval: timedelta = timedelta(hours=1),
    start: datetime = START,
) -> PriceTimeline:
    points = tuple(
        PricePoint(
            start + index * interval,
            start + (index + 1) * interval,
            price,
            "test.provider",
        )
        for index, price in enumerate(prices)
    )
    return PriceTimeline(
        points,
        comparison_starts_at=start,
        comparison_ends_at=start + len(points) * interval,
    )


@pytest.mark.parametrize(
    ("level", "cheap", "expensive"),
    [(1, 2, 9), (2, 3, 9), (3, 3, 8), (4, 4, 7), (5, 4, 6)],
)
def test_levels_use_deterministic_nearest_rank_thresholds(
    level: int, cheap: float, expensive: float
) -> None:
    plan = build_shadow_price_plan(
        timeline=timeline(list(range(1, 11))),
        saving_level=level,
        evaluated_at=START + timedelta(minutes=30),
    )

    assert plan.status is PricePreviewStatus.CLASSIFIED
    assert plan.current_band is PriceBand.CHEAP
    assert plan.thresholds is not None
    assert plan.thresholds.cheap_price == cheap
    assert plan.thresholds.expensive_price == expensive


def test_level_zero_disables_preview_even_with_complete_prices() -> None:
    plan = build_shadow_price_plan(
        timeline=timeline([1, 2, 3, 4]),
        saving_level=0,
        evaluated_at=START,
    )

    assert plan.status is PricePreviewStatus.DISABLED
    assert plan.reason is PricePreviewReason.SAVING_LEVEL_ZERO
    assert plan.current_band is PriceBand.UNKNOWN
    assert plan.thresholds is None


@pytest.mark.parametrize(
    "price_timeline",
    [None, PriceTimeline((), START, START + timedelta(hours=24))],
)
def test_missing_or_empty_timeline_is_unavailable(price_timeline) -> None:
    plan = build_shadow_price_plan(
        timeline=price_timeline,
        saving_level=3,
        evaluated_at=START,
    )

    assert plan.status is PricePreviewStatus.UNAVAILABLE
    assert plan.reason is PricePreviewReason.PRICE_TIMELINE_MISSING


def test_too_few_points_are_explicitly_uninformative() -> None:
    plan = build_shadow_price_plan(
        timeline=timeline([1, 2, 3]),
        saving_level=3,
        evaluated_at=START,
    )

    assert plan.status is PricePreviewStatus.UNINFORMATIVE
    assert plan.reason is PricePreviewReason.TOO_FEW_PRICE_POINTS


def test_flat_prices_are_normal_but_not_presented_as_a_signal() -> None:
    plan = build_shadow_price_plan(
        timeline=timeline([0.5] * 24),
        saving_level=5,
        evaluated_at=START,
    )

    assert plan.status is PricePreviewStatus.UNINFORMATIVE
    assert plan.reason is PricePreviewReason.PRICE_THRESHOLDS_NOT_SEPARATED
    assert plan.current_band is PriceBand.NORMAL


def test_duplicate_values_can_make_distinct_prices_uninformative() -> None:
    plan = build_shadow_price_plan(
        timeline=timeline([1, 1, 1, 1, 2]),
        saving_level=3,
        evaluated_at=START,
    )

    assert plan.status is PricePreviewStatus.UNINFORMATIVE
    assert plan.reason is PricePreviewReason.PRICE_THRESHOLDS_NOT_SEPARATED


@pytest.mark.parametrize(
    ("index", "expected"), [(2, PriceBand.CHEAP), (7, PriceBand.EXPENSIVE)]
)
def test_threshold_boundaries_are_inclusive(index: int, expected: PriceBand) -> None:
    plan = build_shadow_price_plan(
        timeline=timeline(list(range(1, 11))),
        saving_level=3,
        evaluated_at=START + timedelta(hours=index, minutes=30),
    )

    assert plan.current_band is expected


def test_negative_prices_are_valid_relative_values() -> None:
    plan = build_shadow_price_plan(
        timeline=timeline([-1.0, -0.5, 0.0, 0.5, 1.0]),
        saving_level=3,
        evaluated_at=START + timedelta(minutes=30),
    )

    assert plan.current_price == -1.0
    assert plan.current_band is PriceBand.CHEAP


def test_current_gap_is_not_filled_from_a_neighbouring_point() -> None:
    points = list(timeline([1, 2, 3, 4, 5]).points)
    shifted = tuple(
        PricePoint(
            point.starts_at + timedelta(hours=1),
            point.ends_at + timedelta(hours=1),
            point.price_per_kwh,
            point.source,
        )
        for point in points[2:]
    )
    gapped = PriceTimeline(
        (points[0], points[1], *shifted),
        START,
        START + timedelta(hours=6),
    )

    plan = build_shadow_price_plan(
        timeline=gapped,
        saving_level=3,
        evaluated_at=START + timedelta(hours=2, minutes=30),
    )

    assert plan.status is PricePreviewStatus.UNAVAILABLE
    assert plan.reason is PricePreviewReason.PRICE_TIMELINE_GAP
    assert plan.current_band is PriceBand.UNKNOWN


def test_incomplete_comparison_period_is_not_classified() -> None:
    gapped = PriceTimeline(
        (
            *timeline([1, 2, 3, 4]).points,
            PricePoint(
                START + timedelta(hours=5),
                START + timedelta(hours=6),
                5,
                "test.provider",
            ),
        ),
        START,
        START + timedelta(hours=6),
    )

    plan = build_shadow_price_plan(
        timeline=gapped,
        saving_level=3,
        evaluated_at=START + timedelta(minutes=30),
    )

    assert plan.status is PricePreviewStatus.UNAVAILABLE
    assert plan.reason is PricePreviewReason.PRICE_TIMELINE_GAP
    assert plan.current_band is PriceBand.UNKNOWN


def test_interval_boundary_selects_the_next_point() -> None:
    plan = build_shadow_price_plan(
        timeline=timeline([1, 10, 2, 3]),
        saving_level=3,
        evaluated_at=START + timedelta(hours=1),
    )

    assert plan.current_price == 10
    assert plan.current_band is PriceBand.EXPENSIVE


@pytest.mark.parametrize("slot_count", [92, 96, 100])
def test_quarter_hour_timeline_has_no_day_length_assumption(slot_count: int) -> None:
    plan = build_shadow_price_plan(
        timeline=timeline(
            [float(index % 11) for index in range(slot_count)],
            interval=timedelta(minutes=15),
        ),
        saving_level=4,
        evaluated_at=START + timedelta(minutes=7),
    )

    assert plan.status is PricePreviewStatus.CLASSIFIED
    assert plan.point_count == slot_count


@pytest.mark.parametrize(
    "local_start",
    [
        datetime(2026, 3, 29, tzinfo=ZoneInfo("Europe/Stockholm")),
        datetime(2026, 10, 25, tzinfo=ZoneInfo("Europe/Stockholm")),
    ],
)
def test_real_stockholm_dst_tariff_days_are_exact_utc_periods(
    local_start: datetime,
) -> None:
    local_end = local_start + timedelta(days=1)
    utc_start = local_start.astimezone(UTC)
    utc_end = local_end.astimezone(UTC)
    slots = int((utc_end - utc_start) / timedelta(minutes=15))

    price_timeline = timeline(
        [float(index % 11) for index in range(slots)],
        interval=timedelta(minutes=15),
        start=utc_start,
    )
    plan = build_shadow_price_plan(
        timeline=price_timeline,
        saving_level=3,
        evaluated_at=utc_start,
    )

    assert slots in (92, 100)
    assert price_timeline.comparison_ends_at == utc_end
    assert plan.status is PricePreviewStatus.CLASSIFIED


@pytest.mark.parametrize("bad_price", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_prices_are_rejected(bad_price: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        PricePoint(START, START + timedelta(hours=1), bad_price, "test.provider")


def test_invalid_intervals_ordering_and_overlap_are_rejected() -> None:
    with pytest.raises(ValueError, match="later"):
        PricePoint(START, START, 1, "test.provider")
    first = PricePoint(START, START + timedelta(hours=2), 1, "test.provider")
    overlapping = PricePoint(
        START + timedelta(hours=1), START + timedelta(hours=3), 2, "test.provider"
    )
    with pytest.raises(ValueError, match="overlap"):
        PriceTimeline((first, overlapping), START, START + timedelta(hours=3))
    with pytest.raises(ValueError, match="sorted"):
        PriceTimeline((overlapping, first), START, START + timedelta(hours=3))


def test_timeline_rejects_mixed_resolution_source_and_currency() -> None:
    first = PricePoint(START, START + timedelta(hours=1), 1, "provider.one")
    mixed_resolution = PricePoint(
        START + timedelta(hours=1),
        START + timedelta(hours=1, minutes=15),
        2,
        "provider.one",
    )
    mixed_source = PricePoint(
        START + timedelta(hours=1),
        START + timedelta(hours=2),
        2,
        "provider.two",
    )
    with pytest.raises(ValueError, match="interval duration"):
        PriceTimeline((first, mixed_resolution), START, START + timedelta(hours=2))
    with pytest.raises(ValueError, match="one source"):
        PriceTimeline((first, mixed_source), START, START + timedelta(hours=2))
    with pytest.raises(ValueError, match="currency must be SEK"):
        PricePoint(START, START + timedelta(hours=1), 1, "provider.one", "EUR")


def test_datetime_contract_requires_utc() -> None:
    naive = START.replace(tzinfo=None)
    non_utc = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        PricePoint(naive, naive + timedelta(hours=1), 1, "test.provider")
    with pytest.raises(ValueError, match="must use UTC"):
        PricePoint(non_utc, non_utc + timedelta(hours=1), 1, "test.provider")


def test_shadow_plan_is_immutable_and_has_no_control_authority() -> None:
    plan = build_shadow_price_plan(
        timeline=timeline([1, 2, 3, 4]),
        saving_level=3,
        evaluated_at=START,
    )

    with pytest.raises(FrozenInstanceError):
        plan.saving_level = 5
    assert plan.may_control_heat_pump is False
    assert plan.may_request_preheat is False
    assert plan.may_request_curtailment is False
    assert not hasattr(plan, "heating_request")
    assert not hasattr(plan, "curtailment")


def test_shadow_plan_rejects_contradictory_public_states() -> None:
    thresholds = PriceThresholds(1, 4, 30, 80, 4)
    with pytest.raises(ValueError, match="known band"):
        ShadowPricePlan(
            START,
            3,
            PricePreviewStatus.CLASSIFIED,
            PricePreviewReason.PRICE_CLASSIFIED,
            thresholds=thresholds,
            current_price=2,
            point_count=4,
        )
    with pytest.raises(ValueError, match="cannot contain price details"):
        ShadowPricePlan(
            START,
            0,
            PricePreviewStatus.DISABLED,
            PricePreviewReason.SAVING_LEVEL_ZERO,
            current_price=2,
        )
    with pytest.raises(ValueError, match="incompatible reason"):
        ShadowPricePlan(
            START,
            3,
            PricePreviewStatus.UNAVAILABLE,
            PricePreviewReason.PRICE_CLASSIFIED,
        )


@pytest.mark.parametrize(
    "thresholds",
    [
        (5, 1, 30, 80, 4),
        (1, 5, 30.0, 80, 4),
        (1, 5, True, 80, 4),
    ],
)
def test_thresholds_reject_invalid_order_and_percentile_types(thresholds) -> None:
    with pytest.raises((TypeError, ValueError)):
        PriceThresholds(*thresholds)


def test_classified_plan_cross_validates_level_sample_count_and_band() -> None:
    level_three = PriceThresholds(1, 4, 30, 80, 4)
    level_one = PriceThresholds(1, 4, 20, 90, 4)
    with pytest.raises(ValueError, match="match saving level"):
        ShadowPricePlan(
            START,
            5,
            PricePreviewStatus.CLASSIFIED,
            PricePreviewReason.PRICE_CLASSIFIED,
            PriceBand.NORMAL,
            2,
            level_one,
            4,
        )
    with pytest.raises(ValueError, match="enough price points"):
        ShadowPricePlan(
            START,
            3,
            PricePreviewStatus.CLASSIFIED,
            PricePreviewReason.PRICE_CLASSIFIED,
            PriceBand.NORMAL,
            2,
            PriceThresholds(1, 4, 30, 80, 3),
            3,
        )
    with pytest.raises(ValueError, match="band must match"):
        ShadowPricePlan(
            START,
            3,
            PricePreviewStatus.CLASSIFIED,
            PricePreviewReason.PRICE_CLASSIFIED,
            PriceBand.CHEAP,
            2,
            level_three,
            4,
        )


def test_unseparated_result_requires_equal_threshold_prices() -> None:
    with pytest.raises(ValueError, match="must have equal prices"):
        ShadowPricePlan(
            START,
            3,
            PricePreviewStatus.UNINFORMATIVE,
            PricePreviewReason.PRICE_THRESHOLDS_NOT_SEPARATED,
            PriceBand.NORMAL,
            2,
            PriceThresholds(1, 4, 30, 80, 4),
            4,
        )


@pytest.mark.parametrize("level", range(6))
def test_creating_price_preview_cannot_change_comfort_engine(level: int) -> None:
    observation = Observation(
        captured_at=START,
        indoor=SensorReading(20, START, Unit.CELSIUS, "sensor.indoor"),
        outdoor=SensorReading(-5, START, Unit.CELSIUS, "sensor.outdoor"),
    )

    def comfort_cycle():
        return ControlEngine().step(
            observation=observation,
            comfort_policy=ComfortPolicy(),
            safety_policy=SafetyPolicy(),
            state=EngineState(),
            now_utc=START,
            dt=timedelta(minutes=1),
            shadow=True,
        )

    before = comfort_cycle()
    build_shadow_price_plan(
        timeline=timeline([1, 2, 3, 4]),
        saving_level=level,
        evaluated_at=START,
    )
    after = comfort_cycle()

    assert after.requested_decision == before.requested_decision
    assert after.supervised_output == before.supervised_output
    assert after.next_state.comfort == before.next_state.comfort
    assert after.apply_physical is False
