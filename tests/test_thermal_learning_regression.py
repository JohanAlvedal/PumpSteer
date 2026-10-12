"""Thermal Learning regression tests against the latest main control code.

These tests never modify controller behavior. Expected failures document
missing confidence and validation capabilities separately from working fitting.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.thermal_model import ThermalModel


_START = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def _feed_cooling(
    model: ThermalModel,
    *,
    minutes: int,
    start_minute: int = 0,
    drop_per_minute: float = 0.01,
) -> None:
    """Supply one-minute observations from a deterministic cooling trace."""
    for minute in range(start_minute, start_minute + minutes):
        indoor = 21.0 - minute * drop_per_minute
        model.record_temp(_START + timedelta(minutes=minute), indoor)
        model.collect_braking_sample(indoor, 5.0)


def test_fewer_than_20_accepted_samples_do_not_fit():
    model = ThermalModel()
    _feed_cooling(model, minutes=22)

    assert model.pending_samples == 19
    model.fit()

    assert model.is_valid is False
    assert model.sample_count == 0
    assert model.pending_samples == 19


def test_20_accepted_samples_are_enough_without_100():
    model = ThermalModel()
    _feed_cooling(model, minutes=23)

    assert model.pending_samples == 20
    model.fit()

    assert model.is_valid is True
    assert model.sample_count == 20
    assert model.pending_samples == 0


def test_94_sample_fit_estimates_plausible_cooling_constant():
    model = ThermalModel()
    _feed_cooling(model, minutes=97)

    assert model.pending_samples == 94
    model.fit()

    assert model.is_valid is True
    assert model.sample_count == 94
    assert 0.035 < model.k < 0.042
    assert model.pending_samples == 0


@pytest.mark.parametrize("drop_per_minute", [0.0, -0.01])
def test_flat_or_warming_temperature_does_not_count_as_cooling(drop_per_minute):
    model = ThermalModel()
    _feed_cooling(model, minutes=30, drop_per_minute=drop_per_minute)

    assert model.pending_samples == 0
    assert model.is_valid is False


def test_unfitted_model_keeps_samples_until_a_fit_is_possible():
    model = ThermalModel()
    _feed_cooling(model, minutes=22)
    model.fit()
    _feed_cooling(model, minutes=1, start_minute=22)

    assert model.pending_samples == 20
    model.fit()
    assert model.sample_count == 20


def test_restored_k_does_not_generate_fake_temperature_samples():
    model = ThermalModel()
    model.restore_k(0.0162)

    assert model.is_valid is True
    assert model.k == pytest.approx(0.0162)
    assert model.sample_count == 0
    assert model.pending_samples == 0


def test_predicted_drop_increases_with_cold_and_duration():
    model = ThermalModel()
    model.restore_k(0.0162)

    mild_30m = model.predict_drop(21.0, 10.0, 30.0)
    cold_30m = model.predict_drop(21.0, 0.0, 30.0)
    cold_60m = model.predict_drop(21.0, 0.0, 60.0)

    assert 0.0 < mild_30m < cold_30m < cold_60m


@pytest.mark.xfail(
    reason="main has no ThermalModel.confidence property yet; a fitted model can display 0%",
    strict=False,
)
def test_successful_94_sample_fit_has_nonzero_confidence():
    model = ThermalModel()
    _feed_cooling(model, minutes=97)
    model.fit()

    assert model.sample_count == 94
    assert model.confidence > 0.0


@pytest.mark.xfail(
    reason="main does not expose thermal_confidence in PumpSteer sensor attributes",
    strict=False,
)
def test_pumpsteer_exposes_confidence_for_dashboard():
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _: None))
    entry = SimpleNamespace(entry_id="thermal-regression", data={}, options={})
    sensor = PumpSteerSensor(hass, entry)
    sensor._thermal_model.restore_k(0.0162)

    attrs = sensor._base_attrs(
        indoor=21.0,
        target=21.0,
        outdoor=5.0,
        price_category="normal",
        aggressiveness=3,
    )

    assert "thermal_confidence" in attrs
    assert isinstance(attrs["thermal_confidence"], (float, int))


@pytest.mark.xfail(
    reason="main does not yet count and validate completed Thermal Learning sessions",
    strict=False,
)
def test_fitted_model_completes_a_validated_braking_session():
    model = ThermalModel()
    model.restore_k(0.05)
    start = _START

    model.start_validation_session(start, indoor_temp=21.0, outdoor_temp=5.0)
    model.update_validation_session(5.0)
    counted = model.end_validation_session(
        start + timedelta(minutes=60), indoor_temp=20.2
    )

    assert counted is True
    assert model.learning_sessions == 1
    assert model.validated_sessions == 1
    assert model.prediction_mae == pytest.approx(0.0)


@pytest.mark.xfail(
    reason="main restores k only, not the model quality needed to preserve confidence",
    strict=False,
)
def test_restart_can_restore_confidence_quality_summary():
    restored = ThermalModel()
    restored.restore_k(0.0162)
    restored.restore_diagnostics(
        sample_count=94,
        fit_rmse=0.1,
        learning_sessions=2,
        validated_sessions=1,
        prediction_mae=0.2,
    )

    assert restored.sample_count == 94
    assert restored.confidence > 0.0
