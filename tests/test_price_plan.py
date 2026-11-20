"""Tests for the display-only price_plan attribute."""

from datetime import datetime, timedelta, timezone

from custom_components.pumpsteer.sensor import PumpSteerSensor

build = PumpSteerSensor._build_price_plan
TZ = timezone(timedelta(hours=1))


def test_plan_starts_at_current_slot_and_spans_24h():
    now = datetime(2026, 1, 15, 18, 20, tzinfo=TZ)
    prices = [float(i) for i in range(96 * 2)]  # 15-min slots, today + tomorrow
    cats = ["normal"] * len(prices)
    current = 18 * 4 + 1
    plan = build(prices, cats, 15, current, now)
    assert len(plan) == 96
    assert plan[0]["price"] == float(current)
    first = datetime.fromisoformat(plan[0]["start"])
    assert first == datetime(2026, 1, 15, 18, 15, tzinfo=TZ)


def test_plan_truncates_at_end_of_known_prices():
    now = datetime(2026, 1, 15, 22, 0, tzinfo=TZ)
    prices = [1.0] * 24
    plan = build(prices, ["cheap"] * 24, 60, 22, now)
    assert [p["category"] for p in plan] == ["cheap", "cheap"]


def test_plan_empty_on_mismatched_input():
    now = datetime(2026, 1, 15, 22, 0, tzinfo=TZ)
    assert build([], [], 60, 0, now) == []
    assert build([1.0, 2.0], ["cheap"], 60, 0, now) == []
