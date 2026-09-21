import builtins
from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.pumpsteer.utils import (
    compute_price_slot_index,
    detect_price_interval_minutes,
    get_price_window_for_hours,
    get_version,
)


def test_get_version_reads_manifest():
    # FIX: updated to match the current version in manifest.json
    assert get_version() == "2.2.0-beta.2"


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


def test_compute_price_slot_index_handles_spring_dst_transition():
    stockholm = ZoneInfo("Europe/Stockholm")
    current_time = datetime(2026, 3, 29, 3, 0, tzinfo=stockholm)

    index = compute_price_slot_index(current_time, 15, 92)

    assert index == 8


def test_compute_price_slot_index_handles_repeated_autumn_hour():
    stockholm = ZoneInfo("Europe/Stockholm")
    first_0200 = datetime(2026, 10, 25, 2, 0, tzinfo=stockholm, fold=0)
    second_0200 = datetime(2026, 10, 25, 2, 0, tzinfo=stockholm, fold=1)

    assert compute_price_slot_index(first_0200, 15, 100) == 8
    assert compute_price_slot_index(second_0200, 15, 100) == 12


def test_get_price_window_for_hours_returns_expected_slice():
    prices = [float(i) for i in range(10)]
    # FIX: the parameter is named current_slot, not current_slot_index
    window = get_price_window_for_hours(
        prices, current_slot=2, hours=3, price_interval_minutes=60
    )
    assert window == [2.0, 3.0, 4.0]
