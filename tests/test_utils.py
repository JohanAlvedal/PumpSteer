import builtins
from datetime import datetime

from custom_components.pumpsteer.utils import (
    get_version,
    detect_price_interval_minutes,
    compute_price_slot_index,
    hours_to_intervals,
    intervals_to_hours,
    aggregate_price_series,
    get_price_window_for_hours,
)
from custom_components.pumpsteer import compat


def test_get_version_reads_manifest():
    assert get_version() == "1.6.0"


def test_get_version_missing_manifest(monkeypatch):
    def fake_open(*args, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(builtins, "open", fake_open)
    assert get_version() == "unknown"


def test_detect_price_interval_minutes_for_hourly_data():
    prices = [float(i) for i in range(24)]
    assert detect_price_interval_minutes(prices) == 60


def test_detect_price_interval_minutes_for_quarter_hour_data():
    prices = [float(i) for i in range(96)]
    assert detect_price_interval_minutes(prices) == 15


def test_compute_price_slot_index_for_quarter_hour_series():
    moment = datetime(2024, 10, 1, 12, 30)
    assert compute_price_slot_index(moment, 15, 96) == 50


def test_hours_interval_conversions():
    assert hours_to_intervals(3, 60) == 3
    assert hours_to_intervals(3, 15) == 12
    assert intervals_to_hours(12, 15) == 3.0


def test_aggregate_price_series_to_hourly():
    prices = [float(i) for i in range(8)]  # Two hours of quarter-hour data
    aggregated = aggregate_price_series(prices, 15, 60)
    assert aggregated == [1.5, 5.5]


def test_get_price_window_for_hours_respects_duration():
    prices = [float(i) for i in range(96)]
    window = get_price_window_for_hours(prices, start_index=4, hours=3, interval_minutes=15)
    assert len(window) == 12
    assert window[0] == prices[4]


def test_compat_detect_price_interval_minutes_fallback(monkeypatch):
    import custom_components.pumpsteer.utils as utils_module

    monkeypatch.delattr(utils_module, "detect_price_interval_minutes", raising=False)
    prices = [float(i) for i in range(96)]
    assert compat.detect_price_interval_minutes(prices) == 15
