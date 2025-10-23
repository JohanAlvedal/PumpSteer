import builtins
from datetime import datetime

from custom_components.pumpsteer.utils import (
    compute_price_slot_index,
    detect_price_interval_minutes,
    get_price_window_for_hours,
    get_version,
)


def test_get_version_reads_manifest():
    assert get_version() == "1.6.0"


def test_get_version_missing_manifest(monkeypatch):
    def fake_open(*args, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(builtins, "open", fake_open)
    assert get_version() == "unknown"


def test_detect_price_interval_minutes_hourly():
    hourly_prices = [1.0] * 24
    assert detect_price_interval_minutes(hourly_prices) == 60


def test_compute_price_slot_index_clamps_to_range():
    current_time = datetime(2023, 1, 1, 23, 59)
    index = compute_price_slot_index(current_time, 60, 24)
    assert index == 23


def test_get_price_window_for_hours_returns_expected_slice():
    prices = [float(i) for i in range(10)]
    window = get_price_window_for_hours(prices, current_slot_index=2, hours=3, price_interval_minutes=60)
    assert window == [2.0, 3.0, 4.0]
