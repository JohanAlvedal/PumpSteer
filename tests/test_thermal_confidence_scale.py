"""Thermal confidence must be judged against the size of the drops it predicts.

Based on the 2026-11-26 install: ~30 min brake sessions with ~0.06 °C actual
drop, prediction MAE 0.13 °C, yet confidence reported 92 %.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.thermal_model import ThermalModel

_START = datetime(2026, 11, 26, 14, 15, tzinfo=timezone.utc)


def _run_session(model, minutes, start_indoor, end_indoor, outdoor):
    model.start_validation_session(_START, start_indoor, outdoor)
    for minute in range(1, minutes + 1):
        indoor = start_indoor - (start_indoor - end_indoor) * minute / minutes
        assert model.update_validation_session(
            _START + timedelta(minutes=minute), indoor, outdoor
        )
    model.end_validation_session(_START + timedelta(minutes=minutes), end_indoor)


def _good_fit_model(k=0.002):
    model = ThermalModel()
    model.restore_k(k)
    model.restore_diagnostics(sample_count=240, fit_rmse=0.18, learning_sessions=90)
    return model


def test_short_session_counts_as_learning_but_not_as_validation():
    model = _good_fit_model()
    _run_session(model, 30, 20.96, 20.90, -4.8)

    assert model.learning_sessions == 91
    assert model.validated_sessions == 0
    assert model.prediction_mae is None


def test_long_session_below_sensor_resolution_does_not_validate():
    model = _good_fit_model()
    _run_session(model, 90, 20.96, 20.90, -4.8)

    assert model.validated_sessions == 0


def test_restored_small_mae_on_tiny_drops_no_longer_gives_high_confidence():
    """Restored pre-fix state has MAE but no mean drop: judge on sensor scale."""
    model = _good_fit_model()
    model.restore_diagnostics(
        sample_count=240,
        fit_rmse=0.18,
        learning_sessions=90,
        validated_sessions=27,
        prediction_mae=0.13,
    )

    assert model.relative_prediction_error == pytest.approx(1.3)
    assert model.confidence == pytest.approx(0.5)


def test_accurate_predictions_of_real_drops_keep_high_confidence():
    model = _good_fit_model(k=0.015)
    # Predicted 0.015 × 16 × 2 h = 0.48 °C, actual 0.45 °C.
    _run_session(model, 120, 21.0, 20.55, 5.0)

    assert model.validated_sessions == 1
    assert model.validation_mean_drop == pytest.approx(0.45)
    assert model.relative_prediction_error == pytest.approx(0.03 / 0.45, abs=0.01)
    assert model.confidence > 0.85


def test_flat_session_against_large_prediction_lowers_confidence():
    model = _good_fit_model(k=0.0205)
    _run_session(model, 270, 21.2, 21.2, 7.0)

    assert model.validated_sessions == 1
    assert model.validation_mean_drop == pytest.approx(0.0)
    assert model.confidence == pytest.approx(0.5)


def test_mean_drop_survives_restart_and_resets_on_refit():
    model = _good_fit_model(k=0.015)
    _run_session(model, 120, 21.0, 20.55, 5.0)

    reloaded = ThermalModel()
    reloaded.restore_k(model.k)
    reloaded.restore_diagnostics(
        sample_count=model.sample_count,
        fit_rmse=model.fit_rmse,
        learning_sessions=model.learning_sessions,
        validated_sessions=model.validated_sessions,
        prediction_mae=model.prediction_mae,
        validation_mean_drop=model.validation_mean_drop,
    )
    assert reloaded.confidence == pytest.approx(model.confidence)

    for minute in range(30):
        indoor = round(21.0 - 0.01 * minute, 2)
        reloaded.record_temp(_START + timedelta(minutes=minute), indoor)
        reloaded.collect_braking_sample(indoor, 5.0)
    assert reloaded.fit() is True
    assert reloaded.validation_mean_drop is None


def test_expected_drop_rate_is_k_times_delta_and_none_when_unfitted():
    assert ThermalModel().expected_drop_rate(21.0, -5.0) is None

    model = _good_fit_model(k=0.002)
    assert model.expected_drop_rate(21.0, -5.0) == pytest.approx(0.052)
    assert model.expected_drop_rate(21.0, 25.0) == pytest.approx(0.0)
    assert model.expected_drop_rate(None, -5.0) is None


def test_sensor_exposes_new_thermal_attributes():
    sensor = PumpSteerSensor(
        SimpleNamespace(states=SimpleNamespace(get=lambda _: None)),
        SimpleNamespace(entry_id="thermal-scale-test", data={}, options={}),
    )
    sensor._thermal_model.restore_k(0.002)
    sensor._thermal_model.restore_diagnostics(
        sample_count=240, validated_sessions=27, prediction_mae=0.13
    )
    attrs = sensor._base_attrs(20.91, 20.5, -4.78, "expensive", 3)

    assert attrs["thermal_expected_drop_c_per_hour"] == pytest.approx(0.051, abs=1e-3)
    assert attrs["thermal_relative_prediction_error"] == pytest.approx(1.3)
    assert attrs["thermal_validation_mean_drop_c"] is None
