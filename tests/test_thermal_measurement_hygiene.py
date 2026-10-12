"""Only contiguous, valid temperature observations may form cooling rates."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.pumpsteer import sensor as sensor_module
from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.thermal_model import ThermalModel


def _sensor():
    prices = [1.0] * 96
    prices[32:34] = [10.0] * 2
    states = {
        "sensor.indoor": SimpleNamespace(state="20.5", attributes={}),
        "sensor.outdoor": SimpleNamespace(state="5", attributes={}),
        "sensor.price": SimpleNamespace(state="1", attributes={"today": prices}),
    }
    entry = SimpleNamespace(
        entry_id="thermal-hygiene-test",
        data={},
        options={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "electricity_price_entity": "sensor.price",
            "target_temperature": 21,
            "summer_threshold": 18,
            "aggressiveness": 3,
            "house_inertia": 2,
            "preheat_boost_enabled": False,
        },
    )
    return PumpSteerSensor(
        SimpleNamespace(states=SimpleNamespace(get=states.get)), entry
    ), states


def _cycle(sensor, monkeypatch, minute):
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc) + timedelta(minutes=minute)
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: now)
    asyncio.run(sensor._do_update())


@pytest.mark.parametrize(
    "missing", [None, "unknown", "unavailable", "nan", "inf", "bad"]
)
def test_missing_indoor_does_not_record_an_invented_zero(monkeypatch, missing):
    sensor, states = _sensor()
    _cycle(sensor, monkeypatch, 0)
    if missing is None:
        states.pop("sensor.indoor")
    else:
        states["sensor.indoor"].state = missing
    _cycle(sensor, monkeypatch, 1)
    assert sensor.extra_state_attributes["mode"] == "safe_mode"
    assert not sensor._thermal_model._temp_history


def test_real_zero_degree_indoor_observation_is_retained(monkeypatch):
    sensor, states = _sensor()
    states["sensor.indoor"].state = "0"
    _cycle(sensor, monkeypatch, 0)
    assert [temp for _, temp in sensor._thermal_model._temp_history] == [0.0]


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -float("inf")])
def test_invalid_model_observation_breaks_rate_history(bad):
    model = ThermalModel()
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    model.record_temp(now, 21.0)
    model.record_temp(now + timedelta(minutes=3), 20.9)
    model.record_temp(now + timedelta(minutes=4), bad)
    model.record_temp(now + timedelta(minutes=5), 20.8)
    model.collect_braking_sample(20.8, 5)
    assert model.pending_samples == 0


def test_long_gap_requires_new_contiguous_history():
    model = ThermalModel()
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    model.record_temp(now, 21)
    model.record_temp(now + timedelta(minutes=1), 20.95)
    model.record_temp(now + timedelta(hours=1), 20.5)
    model.collect_braking_sample(20.5, 5)
    assert model.pending_samples == 0
    for minute, temp in ((61, 20.48), (62, 20.46), (63, 20.44)):
        model.record_temp(now + timedelta(minutes=minute), temp)
    model.collect_braking_sample(20.44, 5)
    assert model.pending_samples == 1


@pytest.mark.parametrize("minutes", [[0, 2, 4], [0, 5]])
def test_short_poll_gaps_still_produce_valid_cooling_samples(minutes):
    model = ThermalModel()
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    for minute in minutes:
        model.record_temp(now + timedelta(minutes=minute), 21 - minute * 0.02)
    model.collect_braking_sample(21 - minutes[-1] * 0.02, 5)
    assert model.pending_samples == 1


@pytest.mark.parametrize("last_minute", [4, 5])
def test_duplicate_or_backwards_timestamp_breaks_history(last_minute):
    model = ThermalModel()
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    for minute, temp in ((0, 21), (2, 20.95), (5, 20.9), (last_minute, 20.8)):
        model.record_temp(now + timedelta(minutes=minute), temp)
    model.collect_braking_sample(20.8, 5)
    assert model.pending_samples == 0


def test_restart_restores_k_without_a_rate_sample():
    model = ThermalModel()
    model.restore_k(0.04)
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    model.record_temp(now, 20.5)
    model.collect_braking_sample(20.5, 5)
    assert model.pending_samples == 0
    assert model.k == 0.04


def test_learned_k_remains_diagnostic_in_real_control_cycles(monkeypatch):
    first, _ = _sensor()
    second, _ = _sensor()
    first._thermal_model.restore_k(0.01)
    second._thermal_model.restore_k(0.49)
    for minute in (0, 1, 2):
        _cycle(first, monkeypatch, minute)
        _cycle(second, monkeypatch, minute)
        assert first.extra_state_attributes["mode"] == "braking"
        assert first.state == second.state


@pytest.mark.parametrize("month,day", [(3, 29), (10, 25)])
def test_dst_boundary_rate_uses_real_elapsed_minutes(month, day):
    model = ThermalModel()
    start = datetime(2026, month, day, 0, 58, tzinfo=timezone.utc)
    for minute in range(4):
        now = (start + timedelta(minutes=minute)).astimezone(
            ZoneInfo("Europe/Stockholm")
        )
        model.record_temp(now, 21 - minute * 0.02)
    model.collect_braking_sample(20.94, 5)
    assert model.pending_samples == 1
    assert model._samples[0].rate == pytest.approx(-1.2)


def test_gap_exceeding_five_minutes_breaks_history():
    model = ThermalModel()
    now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    model.record_temp(now, 21)
    model.record_temp(now + timedelta(minutes=5, seconds=1), 20.9)
    model.collect_braking_sample(20.9, 5)
    assert model.pending_samples == 0
