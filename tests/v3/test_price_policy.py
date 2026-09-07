"""Tests for the single PumpSteer V3 economy preference."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from custom_components.pumpsteer.v3.pricing import (
    DEFAULT_SAVING_LEVEL,
    PriceBandPolicy,
    normalize_saving_level,
    price_policy_for_saving_level,
)


@pytest.mark.parametrize(
    ("level", "cheap", "expensive"),
    [
        (1, 20, 90),
        (2, 25, 85),
        (3, 30, 80),
        (4, 35, 70),
        (5, 40, 60),
    ],
)
def test_level_maps_to_one_fixed_internal_policy(
    level: int, cheap: int, expensive: int
) -> None:
    policy = price_policy_for_saving_level(level)

    assert policy.saving_level == level
    assert policy.classification_enabled is True
    assert policy.cheap_percentile == cheap
    assert policy.expensive_percentile == expensive


def test_level_zero_explicitly_disables_price_classification() -> None:
    policy = price_policy_for_saving_level(0)

    assert policy.classification_enabled is False
    assert policy.cheap_percentile is None
    assert policy.expensive_percentile is None


def test_default_is_balanced_level_three() -> None:
    assert DEFAULT_SAVING_LEVEL == 3
    assert price_policy_for_saving_level(DEFAULT_SAVING_LEVEL) == PriceBandPolicy(
        saving_level=3,
        classification_enabled=True,
        cheap_percentile=30,
        expensive_percentile=80,
    )


@pytest.mark.parametrize(
    "value",
    [-1, 6, 2.5, float("nan"), float("inf"), True, None, "invalid"],
)
def test_invalid_levels_are_rejected(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        normalize_saving_level(value)


def test_integral_number_entity_values_are_normalized() -> None:
    assert normalize_saving_level(4.0) == 4
    assert normalize_saving_level("5") == 5


def test_policy_is_immutable_and_has_no_authority_fields() -> None:
    policy = price_policy_for_saving_level(3)

    with pytest.raises(FrozenInstanceError):
        policy.saving_level = 5
    assert not hasattr(policy, "curtailment")
    assert not hasattr(policy, "preheat")
    assert not hasattr(policy, "control_authority")


def test_policy_type_rejects_noncanonical_combinations() -> None:
    with pytest.raises(ValueError, match="must be disabled"):
        PriceBandPolicy(0, True, 0, 100)
    with pytest.raises(ValueError, match="require classification"):
        PriceBandPolicy(4, False, None, None)
    with pytest.raises(ValueError, match="must match"):
        PriceBandPolicy(4, True, 30, 80)
