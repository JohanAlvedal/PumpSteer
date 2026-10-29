"""Regression tests for thermal-learning bias, refit gating and price rollover.

Based on the 2026-10-28 brake session: k=0.0205 predicted ~1.4 °C drop over
4.5 h while the house dropped ~0.3 °C, the fit after the session wiped the
validation, and a midnight price rollover briefly forced safe mode.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.thermal_model import ThermalModel

_START = datetime(2026, 10, 28, 14, 30, tzinfo=timezone.utc)


def _run_session(model, minutes, start_indoor, end_indoor, outdoor):
    model.start_validation_session(_START, start_indoor, outdoor)
    for minute in range(1, minutes + 1):
        indoor = start_indoor - (start_indoor - end_indoor) * minute / minutes
        assert model.update_validation_session(
            _START + timedelta(minutes=minute), indoor, outdoor
        )
    model.end_validation_session(_START + timedelta(minutes=minutes), end_indoor)


def _feed_quantized(model, minutes, true_rate_c_per_hour, outdoor=7.0):
    """One-minute samples from a 0.1 °C-resolution sensor with a slow true drop."""
    for minute in range(minutes):
        true_temp = 21.2 + true_rate_c_per_hour * minute / 60.0
        reported = round(true_temp, 1)
        model.record_temp(_START + timedelta(minutes=minute), reported)
        model.collect_braking_sample(reported, outdoor)


def test_flat_rates_are_kept_so_quantization_does_not_bias_k_upward():
    model = ThermalModel()
    # True effective k = 0.066 / 14.2 ≈ 0.0046 °C/h per °C.
    _feed_quantized(model, 240, true_rate_c_per_hour=-0.066)
    assert model.fit() is True
    assert model.k == pytest.approx(0.0046, abs=0.003)


def test_fitted_model_is_not_refitted_before_it_has_been_validated():
    model = ThermalModel()
    model.restore_k(0.0205)
    _run_session(model, 270, 21.2, 20.9, 7.0)
    _feed_quantized(model, 60, true_rate_c_per_hour=-0.066)

    assert model.validated_sessions == 1
    assert model.last_prediction_error is not None
    assert not model.should_refit()


def test_refit_once_validation_shows_consistent_error():
    model = ThermalModel()
    model.restore_k(0.0205)
    for _ in range(3):
        _run_session(model, 270, 21.2, 20.9, 7.0)
    _feed_quantized(model, 60, true_rate_c_per_hour=-0.066)

    assert model.prediction_mae > 0.3
    assert model.should_refit()


def test_unfitted_model_fits_as_soon_as_enough_samples_exist():
    model = ThermalModel()
    _feed_quantized(model, 30, true_rate_c_per_hour=-0.066)
    assert model.should_refit()


def test_flat_session_with_large_predicted_drop_counts_as_validation():
    model = ThermalModel()
    model.restore_k(0.0205)
    _run_session(model, 270, 21.2, 21.2, 7.0)

    assert model.validated_sessions == 1
    assert model.last_prediction_error == pytest.approx(-1.31, abs=0.05)


def test_confidence_is_capped_until_a_prediction_has_been_validated():
    model = ThermalModel()
    model.restore_k(0.015)
    model.restore_diagnostics(sample_count=189, fit_rmse=0.08, learning_sessions=28)
    assert model.confidence == pytest.approx(0.5)

    _run_session(model, 60, 21.0, 20.8, 5.0)
    assert model.validated_sessions == 1
    assert model.confidence > 0.5


def test_last_session_diagnostics_survive_restart():
    model = ThermalModel()
    model.restore_k(0.015)
    model.restore_diagnostics(
        sample_count=189,
        last_prediction_error=-1.088,
        last_session_duration_minutes=270.0,
        last_session_actual_drop=0.3,
        last_session_predicted_drop=1.388,
    )
    assert model.last_prediction_error == pytest.approx(-1.088)
    assert model.last_session_duration_minutes == pytest.approx(270.0)
    assert model.last_session_actual_drop == pytest.approx(0.3)
    assert model.last_session_predicted_drop == pytest.approx(1.388)


def _timestamped_day(start, count=96, interval_minutes=15, offset=0.0):
    return [
        {
            "start": (start + timedelta(minutes=interval_minutes * i)).isoformat(),
            "end": (start + timedelta(minutes=interval_minutes * (i + 1))).isoformat(),
            "value": float(i) + offset,
        }
        for i in range(count)
    ]


def _price_sensor(raw_today, raw_tomorrow):
    states = {
        "sensor.price": SimpleNamespace(
            state="1.0",
            attributes={
                "raw_today": raw_today,
                "raw_tomorrow": raw_tomorrow,
                "unit_of_measurement": "SEK/kWh",
            },
        )
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get, values=states))
    entry = SimpleNamespace(
        entry_id="price-rollover-test",
        data={},
        options={"electricity_price_entity": "sensor.price"},
    )
    return PumpSteerSensor(hass, entry)


def test_unrolled_price_sensor_at_midnight_uses_tomorrow_slots_as_today():
    yesterday = datetime(2026, 10, 28, tzinfo=timezone.utc)
    today = yesterday + timedelta(days=1)
    sensor = _price_sensor(
        _timestamped_day(yesterday), _timestamped_day(today, offset=100.0)
    )
    now = today + timedelta(minutes=5)

    prices, _, interval, slot = asyncio.run(sensor._get_prices(sensor._cfg(), now))

    assert prices[0] == pytest.approx(100.0)
    assert len(prices) == 96
    assert interval == 15
    assert slot == 0


def test_stale_today_without_matching_tomorrow_still_fails_safe():
    two_days_ago = datetime(2026, 10, 27, tzinfo=timezone.utc)
    sensor = _price_sensor(
        _timestamped_day(two_days_ago),
        _timestamped_day(two_days_ago + timedelta(days=1)),
    )
    now = datetime(2026, 10, 29, 0, 5, tzinfo=timezone.utc)

    assert asyncio.run(sensor._get_prices(sensor._cfg(), now)) == ([], [], 60, 0)


def _dst_end_day_wallclock_sorted():
    """SE3 2026-10-25: 100 slots, repeated 02:00 hour sorted by wall-clock time."""
    tz = ZoneInfo("Europe/Stockholm")
    start = datetime(2026, 10, 24, 22, tzinfo=timezone.utc)  # 00:00 local
    slots = []
    for i in range(100):
        # Compute in UTC; aware local arithmetic is wall-clock based.
        slot_start = start + timedelta(minutes=15 * i)
        slot_end = slot_start + timedelta(minutes=15)
        slots.append(
            {
                "start": slot_start.astimezone(tz).isoformat(),
                "end": slot_end.astimezone(tz).isoformat(),
                "value": float(i),
            }
        )
    # Nord Pool orders by local wall-clock time, interleaving the repeated hour.
    slots.sort(
        key=lambda item: datetime.fromisoformat(item["start"]).replace(tzinfo=None)
    )
    return slots


def test_dst_end_day_with_wallclock_sorted_slots_is_accepted():
    raw = _dst_end_day_wallclock_sorted()
    assert raw[9]["start"] == "2026-10-25T02:00:00+01:00"
    sensor = _price_sensor(raw, [])
    now = datetime(2026, 10, 25, 12, tzinfo=ZoneInfo("Europe/Stockholm"))

    prices, _, interval, slot = asyncio.run(sensor._get_prices(sensor._cfg(), now))

    assert prices == [float(i) for i in range(100)]
    assert interval == 15
    # 12:00 local on a 25-hour day is 13 h = 52 slots after midnight.
    assert slot == 52
    assert sensor._current_price == pytest.approx(52.0)


def test_dst_end_day_with_duplicate_slot_still_fails_safe():
    raw = _dst_end_day_wallclock_sorted()
    raw[9] = dict(raw[8])
    sensor = _price_sensor(raw, [])
    now = datetime(2026, 10, 25, 12, tzinfo=ZoneInfo("Europe/Stockholm"))

    assert asyncio.run(sensor._get_prices(sensor._cfg(), now)) == ([], [], 60, 0)
