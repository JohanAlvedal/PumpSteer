"""Tests for ThermalModel learning quality, validation and shadow diagnostics."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401

from custom_components.pumpsteer.electricity_price import PRICE_EXPENSIVE, PRICE_NORMAL
from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.thermal_model import ThermalModel


class _DummyHass:
    states = SimpleNamespace(get=lambda entity_id: None)


class _DummyEntry:
    entry_id = "thermal-test"
    data = {}
    options = {}


def _feed_cooling_samples(
    model: ThermalModel,
    *,
    minutes: int,
    start_indoor: float = 21.0,
    outdoor: float = 5.0,
    drop_per_minute: float = 0.01,
) -> None:
    start = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    for minute in range(minutes):
        indoor = start_indoor - drop_per_minute * minute
        now = start + timedelta(minutes=minute)
        model.record_temp(now, indoor)
        model.collect_braking_sample(indoor, outdoor)


def test_fit_uses_relevant_samples_and_exposes_quality():
    model = ThermalModel()
    _feed_cooling_samples(model, minutes=35)

    assert model.pending_samples >= 20
    assert model.fit() is True
    assert model.is_valid is True
    assert model.sample_count >= 20
    assert model.fit_rmse is not None
    assert model.fit_rmse >= 0.0
    assert model.confidence > 0.0
    assert model.pending_samples == 0


def test_learning_sample_memory_is_bounded():
    model = ThermalModel()
    _feed_cooling_samples(
        model,
        minutes=400,
        drop_per_minute=0.005,
    )

    assert model.pending_samples == 240


def test_restored_k_has_zero_confidence_without_quality_data():
    model = ThermalModel()
    model.restore_k(0.05)

    assert model.is_valid is True
    assert model.confidence == 0.0


def test_short_validation_session_is_ignored():
    model = ThermalModel()
    model.restore_k(0.05)
    start = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)

    model.start_validation_session(start, indoor_temp=21.0, outdoor_temp=5.0)
    counted = model.end_validation_session(
        start + timedelta(minutes=5),
        indoor_temp=20.9,
    )

    assert counted is False
    assert model.learning_sessions == 0
    assert model.validated_sessions == 0


def test_forecast_profile_changes_predicted_drop():
    model = ThermalModel()
    model.restore_k(0.05)

    constant_drop = model.predict_drop(
        indoor=21.0,
        outdoor=5.0,
        duration_minutes=120.0,
    )
    forecast_drop = model.predict_drop_profile(
        indoor=21.0,
        current_outdoor=5.0,
        future_outdoor_temps=[-5.0],
        duration_minutes=120.0,
    )

    assert forecast_drop > constant_drop


def test_fitted_model_validates_session_prediction():
    model = ThermalModel()
    model.restore_k(0.05)
    start = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)

    model.start_validation_session(start, indoor_temp=21.0, outdoor_temp=5.0)
    model.update_validation_session(5.0)
    counted = model.end_validation_session(
        start + timedelta(minutes=60),
        indoor_temp=20.2,
    )

    assert counted is True
    assert model.learning_sessions == 1
    assert model.validated_sessions == 1
    assert model.prediction_mae == pytest.approx(0.0)
    assert model.last_session_actual_drop == pytest.approx(0.8)
    assert model.last_session_predicted_drop == pytest.approx(0.8)


def test_fallback_session_counts_learning_but_not_validation():
    model = ThermalModel()
    start = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)

    model.start_validation_session(start, indoor_temp=21.0, outdoor_temp=5.0)
    counted = model.end_validation_session(
        start + timedelta(minutes=60),
        indoor_temp=20.2,
    )

    assert counted is True
    assert model.learning_sessions == 1
    assert model.validated_sessions == 0
    assert model.prediction_mae is None


@pytest.mark.parametrize(
    ("brake_requested", "factor", "demand", "outdoor", "expected", "reason"),
    [
        (True, 0.80, 1.5, 5.0, True, "active"),
        (False, 0.80, 1.5, 5.0, False, "brake_not_requested"),
        (True, 0.50, 1.5, 5.0, False, "brake_ramp_not_stable"),
        (True, 0.80, 0.2, 5.0, False, "heating_demand_too_low"),
        (True, 0.80, 1.5, 17.0, False, "outdoor_too_warm"),
    ],
)
def test_learning_relevance_requires_real_heating_conditions(
    brake_requested,
    factor,
    demand,
    outdoor,
    expected,
    reason,
):
    active, actual_reason = PumpSteerSensor._thermal_learning_relevance(
        brake_requested=brake_requested,
        brake_factor=factor,
        heating_demand_c=demand,
        outdoor=outdoor,
        summer_threshold=18.0,
    )

    assert active is expected
    assert actual_reason == reason


def test_remaining_expensive_minutes_uses_current_slot_remainder():
    sensor = PumpSteerSensor(_DummyHass(), _DummyEntry())
    now = datetime(2026, 1, 15, 10, 7, tzinfo=timezone.utc)
    categories = [PRICE_EXPENSIVE, PRICE_EXPENSIVE, PRICE_NORMAL]

    remaining = sensor._remaining_expensive_minutes(
        categories,
        current_slot=0,
        interval_minutes=15,
        now=now,
    )

    assert remaining == pytest.approx(23.0)
