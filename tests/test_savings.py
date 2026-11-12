"""Tests for the observational savings estimate (savings.py)."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.savings import (
    MAX_SAMPLE_SECONDS,
    SavingsEstimator,
    SavingsSample,
    price_scale_to_currency,
)

T0 = datetime(2026, 1, 15, 18, 0, tzinfo=UTC)


def sample(t, offset, price, ref=1.0, k=0.1):
    return SavingsSample(
        now=t, offset_c=offset, price=price, reference_price=ref, kwh_per_c_hour=k
    )


def test_first_sample_only_sets_clock():
    est = SavingsEstimator()
    assert est.update(sample(T0, 5.0, 2.0)) == 0.0
    assert est.total == 0.0
    assert est.last_t == T0


def test_braking_at_expensive_price_is_positive():
    est = SavingsEstimator()
    est.update(sample(T0, 5.0, 2.0))
    # 60 s steps for one hour: 0.1 kWh/°C·h * 5 °C * 1 h = 0.5 kWh shifted.
    for i in range(1, 61):
        est.update(sample(T0 + timedelta(minutes=i), 5.0, 2.0))
    assert est.reduced_kwh == pytest.approx(0.5)
    assert est.added_kwh == 0.0
    # 0.5 kWh * (2.0 - 1.0) = 0.5
    assert est.total == pytest.approx(0.5)


def test_preheat_at_cheap_price_is_positive():
    est = SavingsEstimator()
    est.update(sample(T0, -2.0, 0.4))
    est.update(sample(T0 + timedelta(minutes=5), -2.0, 0.4))
    kwh = 0.1 * 2.0 * 5 / 60
    assert est.added_kwh == pytest.approx(kwh)
    assert est.total == pytest.approx(kwh * 0.6)


def test_preheat_at_expensive_price_counts_as_cost():
    est = SavingsEstimator()
    est.update(sample(T0, -2.0, 1.5))
    est.update(sample(T0 + timedelta(minutes=5), -2.0, 1.5))
    assert est.total < 0.0


def test_long_gap_is_capped():
    est = SavingsEstimator()
    est.update(sample(T0, 5.0, 2.0))
    est.update(sample(T0 + timedelta(hours=3), 5.0, 2.0))
    expected_kwh = 0.1 * 5.0 * MAX_SAMPLE_SECONDS / 3600
    assert est.reduced_kwh == pytest.approx(expected_kwh)


@pytest.mark.parametrize(
    "price,ref,k",
    [(None, 1.0, 0.1), (2.0, None, 0.1), (float("nan"), 1.0, 0.1), (2.0, 1.0, 0.0)],
)
def test_missing_or_invalid_inputs_add_nothing_but_advance_clock(price, ref, k):
    est = SavingsEstimator()
    est.update(sample(T0, 5.0, 2.0))
    t1 = T0 + timedelta(minutes=1)
    assert est.update(sample(t1, 5.0, price, ref, k)) == 0.0
    assert est.total == 0.0
    assert est.last_t == t1


def test_clock_going_backwards_adds_nothing():
    est = SavingsEstimator()
    est.update(sample(T0, 5.0, 2.0))
    assert est.update(sample(T0 - timedelta(minutes=1), 5.0, 2.0)) == 0.0


@pytest.mark.parametrize(
    "unit,factor",
    [
        ("SEK/kWh", 1.0),
        ("öre/kWh", 0.01),
        ("EUR/kWh", 1.0),
        ("c/kWh", 0.01),
        (None, 1.0),
        ("", 1.0),
    ],
)
def test_price_scale(unit, factor):
    assert price_scale_to_currency(unit) == factor
