"""Prices must retain their original day and slot identity."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.pumpsteer.electricity_price import PRICE_CHEAP, PRICE_EXPENSIVE
from custom_components.pumpsteer.sensor import PumpSteerSensor


def _sensor(today, tomorrow=None, raw=False):
    states = {
        "sensor.price": SimpleNamespace(
            state="1.0",
            attributes={
                "raw_today" if raw else "today": today,
                "raw_tomorrow" if raw else "tomorrow": tomorrow or [],
                "unit_of_measurement": "SEK/kWh",
            },
        )
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get, values=states))
    entry = SimpleNamespace(
        entry_id="price-slot-test",
        data={},
        options={"electricity_price_entity": "sensor.price"},
    )
    return PumpSteerSensor(hass, entry)


def _prices(sensor, now=None):
    return asyncio.run(
        sensor._get_prices(
            sensor._cfg(), now or datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
        )
    )


@pytest.mark.parametrize("interval", [5, 10, 15, 20, 30, 60, 120])
@pytest.mark.parametrize("position", [0, 0.5, 1])
@pytest.mark.parametrize(
    "bad",
    [
        None,
        "unavailable",
        "bad",
        {},
        {"value": "nan"},
        float("inf"),
        True,
        False,
        {"value": True},
        {"price": False},
    ],
)
def test_invalid_today_slot_fails_safe_instead_of_shifting(interval, position, bad):
    today = [float(i) for i in range(1440 // interval)]
    today[int((len(today) - 1) * position)] = bad
    sensor = _sensor(today, [1000.0] * len(today))

    assert _prices(sensor) == ([], [], 60, 0)
    assert sensor._current_price is None


@pytest.mark.parametrize("position", [0, 12, 23])
@pytest.mark.parametrize("bad", [None, "unknown", "bad", {}, {"price": "inf"}])
def test_invalid_optional_tomorrow_is_discarded_as_a_day(position, bad):
    today = [float(i) for i in range(24)]
    tomorrow = [float(i + 100) for i in range(24)]
    tomorrow[position] = bad
    sensor = _sensor(today, tomorrow)

    prices, categories, interval, slot = _prices(sensor)

    assert prices == today
    assert len(categories) == 24
    assert interval == 60
    assert slot == 12
    assert sensor._current_price == 12.0


@pytest.mark.parametrize("today", [None, [], ["bad"] * 24])
def test_tomorrow_cannot_substitute_for_missing_today(today):
    sensor = _sensor(today, [100.0] * 24)

    assert _prices(sensor) == ([], [], 60, 0)
    assert sensor._current_price is None


def test_valid_negative_zero_and_expensive_slots_keep_classification():
    today = [1.0] * 96
    today[0:2] = [-1.0, 0.0]
    today[48:50] = [8.0, 8.0]  # A full 30-minute peak must survive filtering.
    tomorrow = [-2.0] * 96
    sensor = _sensor(today, tomorrow)

    prices, categories, interval, slot = _prices(sensor)

    assert prices == today + tomorrow
    assert categories[:2] == [PRICE_CHEAP, PRICE_CHEAP]
    assert categories[48:50] == [PRICE_EXPENSIVE, PRICE_EXPENSIVE]
    assert interval == 15
    assert slot == 48
    assert sensor._current_price == 8.0
    assert sensor._current_price_unit == "SEK/kWh"


def test_single_quarter_hour_peak_still_filtered():
    today = [1.0] * 96
    today[48] = 8.0
    _, categories, _, slot = _prices(_sensor(today))
    assert slot == 48
    assert categories[slot] == PRICE_CHEAP


@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize(
    "day,count,hour,minute,fold,expected_slot",
    [
        ((2026, 3, 29), 92, 3, 15, 0, 9),
        ((2026, 3, 29), 92, 23, 45, 0, 91),
        ((2026, 10, 25), 100, 2, 15, 0, 9),
        ((2026, 10, 25), 100, 2, 15, 1, 13),
        ((2026, 10, 25), 100, 23, 45, 0, 99),
        ((2026, 10, 11), 96, 23, 45, 0, 95),
    ],
)
def test_dst_price_slots_keep_elapsed_time_identity(
    raw, day, count, hour, minute, fold, expected_slot
):
    zone = ZoneInfo("Europe/Stockholm")
    now = datetime(*day, hour, minute, tzinfo=zone, fold=fold)
    values = [float(i) for i in range(count)]
    today = values
    if raw:
        start = datetime(*day, tzinfo=zone).astimezone(timezone.utc)
        today = [
            {
                "start": (start + timedelta(minutes=15 * i)).isoformat(),
                "end": (start + timedelta(minutes=15 * (i + 1))).isoformat(),
                "value": value,
            }
            for i, value in enumerate(values)
        ]
    sensor = _sensor(today, raw=raw)

    prices, categories, interval, slot = _prices(sensor, now)

    assert prices == values
    assert len(categories) == count
    assert interval == 15
    assert slot == expected_slot
    assert sensor._current_price == float(expected_slot)


def test_price_issue_recovers_when_today_is_repaired():
    today = [1.0] * 24
    today[3] = None
    sensor = _sensor(today)
    assert _prices(sensor)[0] == []
    today[3] = -0.5

    assert _prices(sensor)[0] == today
    assert sensor._price_issue is None


@pytest.mark.parametrize("interval", [5, 10, 15, 20, 30, 60, 120])
def test_valid_day_retains_slot_interval(interval):
    today = [float(i) for i in range(1440 // interval)]
    sensor = _sensor(today)
    prices, _, actual_interval, slot = _prices(sensor)
    assert prices == today
    assert actual_interval == interval
    assert slot == 720 // interval
    assert sensor._current_price == float(720 // interval)


@pytest.mark.parametrize("count", [23, 25, 95, 97])
def test_incomplete_or_excess_today_cannot_shift_into_tomorrow(count):
    sensor = _sensor([1.0] * count, [100.0] * 24)
    now = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
    assert _prices(sensor, now) == ([], [], 60, 0)


@pytest.mark.parametrize(
    "mutation", ["yesterday", "gap", "naive", "malformed", "partial"]
)
def test_explicit_timestamps_must_match_day_and_slot(mutation):
    start = datetime(2026, 10, 11, tzinfo=timezone.utc)
    today = [
        {
            "start": (start + timedelta(hours=i)).isoformat(),
            "end": (start + timedelta(hours=i + 1)).isoformat(),
            "value": float(i),
        }
        for i in range(24)
    ]
    if mutation == "yesterday":
        for item in today:
            for key in ("start", "end"):
                item[key] = (
                    datetime.fromisoformat(item[key]) - timedelta(days=1)
                ).isoformat()
    elif mutation == "gap":
        today[1]["start"] = today[2]["start"]
        today[1]["end"] = today[2]["end"]
    elif mutation == "naive":
        today[1]["start"] = "2026-10-11T01:00:00"
        today[1]["end"] = "2026-10-11T02:00:00"
    elif mutation == "malformed":
        today[1]["start"] = "not-a-time"
    else:
        today[1].pop("end")
    assert _prices(_sensor(today, raw=True)) == ([], [], 60, 0)


def test_incomplete_optional_tomorrow_keeps_today_only():
    today = [1.0] * 24
    assert _prices(_sensor(today, [100.0] * 23))[0] == today


@pytest.mark.parametrize(
    "day,tomorrow_count", [((2026, 3, 28), 92), ((2026, 10, 24), 100)]
)
def test_tomorrow_length_uses_its_own_dst_day(day, tomorrow_count):
    now = datetime(*day, 12, tzinfo=ZoneInfo("Europe/Stockholm"))
    today = [1.0] * 96
    tomorrow = [2.0] * tomorrow_count
    assert _prices(_sensor(today, tomorrow), now)[0] == today + tomorrow


def test_invalid_today_enters_safe_mode_in_real_update(monkeypatch):
    today = [1.0] * 24
    today[0] = None
    sensor = _sensor(today)
    sensor.hass.states.values.update(
        {
            "sensor.indoor": SimpleNamespace(state="21", attributes={}),
            "sensor.outdoor": SimpleNamespace(state="5", attributes={}),
        }
    )
    sensor._config_entry.options.update(
        indoor_temp_entity="sensor.indoor", real_outdoor_entity="sensor.outdoor"
    )
    from custom_components.pumpsteer import sensor as sensor_module

    monkeypatch.setattr(
        sensor_module.dt_util,
        "now",
        lambda: datetime(2026, 10, 11, 12, tzinfo=timezone.utc),
    )
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == "safe_mode"
    assert sensor.state == 5.0


def _timestamped_day(start, count, interval_minutes=15):
    """Build Nord Pool-style prices carrying an explicit UTC slot timeline."""
    records = []
    for index in range(count):
        slot_start = start + timedelta(minutes=interval_minutes * index)
        slot_end = slot_start + timedelta(minutes=interval_minutes)
        records.append(
            {
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
                "value": float(index),
            }
        )
    return records


def test_timestamped_raw_today_preferred_over_shorter_numeric_today():
    sensor = _sensor([float(i) for i in range(48)])
    attrs = sensor.hass.states.values["sensor.price"].attributes
    start = datetime(2026, 10, 11, tzinfo=timezone.utc)
    attrs["raw_today"] = _timestamped_day(start, 96)

    prices, _, interval, current_slot = _prices(sensor)

    assert prices == [float(i) for i in range(96)]
    assert interval == 15
    assert current_slot == 48
    assert sensor._current_price == 48.0


def test_incomplete_timestamped_raw_today_cannot_fall_back_to_numeric_today():
    sensor = _sensor([float(i) for i in range(96)])
    attrs = sensor.hass.states.values["sensor.price"].attributes
    start = datetime(2026, 10, 11, tzinfo=timezone.utc)
    attrs["raw_today"] = _timestamped_day(start, 48)

    assert _prices(sensor) == ([], [], 60, 0)
    assert sensor._current_price is None


def test_timestamped_raw_tomorrow_preferred_over_shorter_numeric_tomorrow():
    today = [1.0] * 96
    sensor = _sensor(today, [2.0] * 48)
    attrs = sensor.hass.states.values["sensor.price"].attributes
    start = datetime(2026, 10, 12, tzinfo=timezone.utc)
    attrs["raw_tomorrow"] = _timestamped_day(start, 96)

    prices, _, interval, slot = _prices(sensor)

    assert prices[:96] == today
    assert prices[96:] == [float(i) for i in range(96)]
    assert interval == 15
    assert slot == 48


def test_incomplete_raw_tomorrow_is_discarded_without_shifting_today():
    today = [float(i) for i in range(96)]
    sensor = _sensor(today, [2.0] * 96)
    attrs = sensor.hass.states.values["sensor.price"].attributes
    start = datetime(2026, 10, 12, tzinfo=timezone.utc)
    attrs["raw_tomorrow"] = _timestamped_day(start, 48)

    prices, _, interval, slot = _prices(sensor)

    assert prices == today
    assert interval == 15
    assert slot == 48


def test_mixed_timestamped_and_untimestamped_slots_are_rejected():
    start = datetime(2026, 10, 11, tzinfo=timezone.utc)
    today = _timestamped_day(start, 96)
    today[3] = 3.0

    assert _prices(_sensor(today, raw=True)) == ([], [], 60, 0)


def test_partial_timestamped_tomorrow_is_rejected_without_losing_today():
    today = [1.0] * 96
    start = datetime(2026, 10, 12, tzinfo=timezone.utc)
    tomorrow = _timestamped_day(start, 96)
    tomorrow[3] = 3.0

    assert _prices(_sensor(today, tomorrow))[0] == today


def test_numeric_only_half_hour_day_remains_supported():
    # Without timestamps, 48 half-hour prices and truncated quarter-hour prices
    # are indistinguishable; do not reject valid 30-minute price sources.
    today = [float(i) for i in range(48)]
    prices, _, interval, slot = _prices(_sensor(today))
    assert prices == today
    assert interval == 30
    assert slot == 24
