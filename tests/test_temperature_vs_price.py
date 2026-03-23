"""
PumpSteer – Komplett testsvit mot nuvarande arkitektur.

Fixar för de 10 failande testerna:
  - Borttagna anrop till _build_attributes (finns ej längre)
  - safe_float hanterar nu NaN/inf korrekt (fix i utils.py)
  - Holiday parsing fungerar med uppdaterad ha_test_stubs
  - get_price_window_for_hours använder rätt parameternamn (current_slot)
  - Inga referenser till BRAKE_FAKE_TEMP eller HEATING_COMPENSATION_FACTOR

Kör med: pytest tests/ -v
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401 — måste importeras före alla HA-moduler

from custom_components.pumpsteer.electricity_price import (
    classify_price,
    classify_price_list,
    compute_price_thresholds,
    filter_short_peaks,
    PRICE_CHEAP,
    PRICE_NORMAL,
    PRICE_EXPENSIVE,
)
from custom_components.pumpsteer.utils import (
    safe_float,
    get_price_window_for_hours,
    detect_price_interval_minutes,
    compute_price_slot_index,
)
from custom_components.pumpsteer.settings import (
    COMFORT_FLOOR_BY_AGGRESSIVENESS,
    BRAKE_DELTA_C,
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
    ABSOLUTE_CHEAP_LIMIT,
)


# ── Gemensamma test-hjälpklasser ──────────────────────────────────────────────

class DummyState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class DummyStates:
    def __init__(self, mapping=None):
        self._m = mapping or {}

    def get(self, entity_id):
        v = self._m.get(entity_id)
        if v is None:
            return None
        if isinstance(v, dict):
            return DummyState(v.get("state", ""), v.get("attributes", {}))
        return DummyState(v)


class DummyHass:
    def __init__(self, states=None):
        self.states = DummyStates(states or {})


class DummyConfigEntry:
    entry_id = "test"
    data = {}
    options = {}

    def add_update_listener(self, listener):
        pass


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Prisklassificering
# ═════════════════════════════════════════════════════════════════════════════

def test_classify_cheap_below_p30():
    assert classify_price(0.5, p30=1.0, p80=2.0) == PRICE_CHEAP


def test_classify_cheap_via_absolute_limit():
    """Priser under ABSOLUTE_CHEAP_LIMIT är alltid cheap, oavsett historik."""
    assert classify_price(ABSOLUTE_CHEAP_LIMIT - 0.01, p30=0.0, p80=0.0) == PRICE_CHEAP


def test_classify_normal_between_p30_and_p80():
    assert classify_price(1.5, p30=1.0, p80=2.0) == PRICE_NORMAL


def test_classify_expensive_above_p80():
    assert classify_price(2.5, p30=1.0, p80=2.0) == PRICE_EXPENSIVE


def test_classify_price_list_length_preserved():
    prices = [0.5, 1.0, 1.5, 2.0, 2.5]
    cats = classify_price_list(prices, p30=0.8, p80=1.8)
    assert len(cats) == len(prices)


def test_compute_thresholds_uses_history_when_sufficient():
    history = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    today   = [100.0, 200.0]
    p30, p80 = compute_price_thresholds(history, today)
    assert 0 < p30 < p80
    assert p80 < 50.0


def test_compute_thresholds_falls_back_to_today():
    p30, p80 = compute_price_thresholds([], [1.0, 2.0, 3.0, 4.0, 5.0])
    assert p30 < p80


def test_compute_thresholds_empty_returns_zero():
    p30, p80 = compute_price_thresholds([], [])
    assert p30 == 0.0
    assert p80 == 0.0


def test_classify_all_identical_prices():
    """Alla identiska priser ger P30=P80 → allt klassas cheap (price <= p30)."""
    prices = [1.5] * 24
    p30, p80 = compute_price_thresholds(prices, prices)
    cats = classify_price_list(prices, p30, p80)
    # price <= p30 → cheap (p30 == p80 == 1.5, price == 1.5)
    assert all(c == PRICE_CHEAP for c in cats)


# ═════════════════════════════════════════════════════════════════════════════
# 2. filter_short_peaks
# ═════════════════════════════════════════════════════════════════════════════

def test_filter_removes_single_slot_spike():
    cats   = [PRICE_NORMAL, PRICE_EXPENSIVE, PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=120)
    assert PRICE_EXPENSIVE not in result


def test_filter_keeps_long_expensive_block():
    cats   = [PRICE_NORMAL] + [PRICE_EXPENSIVE] * 3 + [PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=120)
    assert result.count(PRICE_EXPENSIVE) == 3


def test_filter_empty_list():
    assert filter_short_peaks([], interval_minutes=60) == []


def test_filter_all_expensive_unchanged():
    cats   = [PRICE_EXPENSIVE] * 5
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=60)
    assert result == cats


def test_filter_replaces_with_left_neighbor():
    cats   = [PRICE_CHEAP, PRICE_EXPENSIVE, PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=120)
    assert result[1] == PRICE_CHEAP


# ═════════════════════════════════════════════════════════════════════════════
# 3. safe_float — inkl. NaN/inf fix
# ═════════════════════════════════════════════════════════════════════════════

def test_safe_float_normal():
    assert safe_float("21.5") == 21.5


def test_safe_float_none():
    assert safe_float(None) is None


def test_safe_float_unavailable():
    assert safe_float("unavailable") is None


def test_safe_float_unknown():
    assert safe_float("unknown") is None


def test_safe_float_below_min():
    assert safe_float(-100.0, min_val=-50.0) is None


def test_safe_float_above_max():
    assert safe_float(100.0, max_val=50.0) is None


def test_safe_float_nan():
    """FIX: NaN ska returnera None, inte float('nan')."""
    assert safe_float(float("nan")) is None


def test_safe_float_positive_inf():
    """FIX: +Inf ska returnera None."""
    assert safe_float(float("inf")) is None


def test_safe_float_negative_inf():
    """FIX: -Inf ska returnera None."""
    assert safe_float(float("-inf")) is None


def test_safe_float_nan_string():
    """Strängen 'nan' ska returnera None."""
    assert safe_float("nan") is None


def test_safe_float_integer_input():
    assert safe_float(5) == 5.0


def test_safe_float_zero():
    assert safe_float(0.0) == 0.0


def test_safe_float_negative():
    assert safe_float(-15.5) == -15.5


# ═════════════════════════════════════════════════════════════════════════════
# 4. get_price_window_for_hours — FIX: rätt parameternamn
# ═════════════════════════════════════════════════════════════════════════════

def test_get_price_window_basic():
    """FIX: parametern heter current_slot, inte current_slot_index."""
    prices = [1.0, 1.5, 2.0, 2.5, 3.0, 1.0]
    result = get_price_window_for_hours(
        prices=prices,
        current_slot=0,          # ← korrekt parameternamn
        hours=2,
        price_interval_minutes=60,
    )
    assert result == [1.0, 1.5]


def test_get_price_window_from_middle():
    prices = [1.0, 1.5, 2.0, 2.5, 3.0]
    result = get_price_window_for_hours(
        prices=prices,
        current_slot=2,
        hours=2,
        price_interval_minutes=60,
    )
    assert result == [2.0, 2.5]


def test_get_price_window_empty_prices():
    result = get_price_window_for_hours(
        prices=[],
        current_slot=0,
        hours=3,
        price_interval_minutes=60,
    )
    assert result == []


def test_get_price_window_15min_intervals():
    """Med 15-min intervall täcker 1 timme 4 slots."""
    prices = list(range(96))  # 96 slots à 15 min = 24h
    result = get_price_window_for_hours(
        prices=prices,
        current_slot=0,
        hours=1,
        price_interval_minutes=15,
    )
    assert len(result) == 4


# ═════════════════════════════════════════════════════════════════════════════
# 5. detect_price_interval_minutes
# ═════════════════════════════════════════════════════════════════════════════

def test_detect_interval_24_hourly():
    assert detect_price_interval_minutes([1.0] * 24) == 60


def test_detect_interval_96_quarter_hourly():
    assert detect_price_interval_minutes([1.0] * 96) == 15


def test_detect_interval_empty():
    assert detect_price_interval_minutes([]) == 60


def test_detect_interval_48_half_hourly():
    assert detect_price_interval_minutes([1.0] * 48) == 30


# ═════════════════════════════════════════════════════════════════════════════
# 6. compute_price_slot_index
# ═════════════════════════════════════════════════════════════════════════════

def test_slot_index_midnight():
    t = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert compute_price_slot_index(t, price_interval_minutes=60, total_slots=24) == 0


def test_slot_index_noon():
    t = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert compute_price_slot_index(t, price_interval_minutes=60, total_slots=24) == 12


def test_slot_index_last_slot_2359():
    """23:59 med 15-min slots ska ge slot 95 (det sista av 96)."""
    t = datetime(2025, 1, 1, 23, 59, tzinfo=timezone.utc)
    assert compute_price_slot_index(t, price_interval_minutes=15, total_slots=96) == 95


def test_slot_index_clamped_to_last():
    """Slot-index ska aldrig överstiga total_slots-1."""
    t = datetime(2025, 1, 1, 23, 59, tzinfo=timezone.utc)
    result = compute_price_slot_index(t, price_interval_minutes=60, total_slots=5)
    assert result <= 4


# ═════════════════════════════════════════════════════════════════════════════
# 7. Comfort floor per aggressiveness
# ═════════════════════════════════════════════════════════════════════════════

def test_comfort_floor_list_has_six_entries():
    assert len(COMFORT_FLOOR_BY_AGGRESSIVENESS) == 6


def test_comfort_floor_aggressiveness_0_is_zero():
    assert COMFORT_FLOOR_BY_AGGRESSIVENESS[0] == 0.0


def test_comfort_floor_aggressiveness_5_is_max():
    assert COMFORT_FLOOR_BY_AGGRESSIVENESS[5] == 2.0


def test_comfort_floor_increases_with_aggressiveness():
    floors = COMFORT_FLOOR_BY_AGGRESSIVENESS
    assert all(floors[i] <= floors[i + 1] for i in range(len(floors) - 1))


# ═════════════════════════════════════════════════════════════════════════════
# 8. PIController
# ═════════════════════════════════════════════════════════════════════════════

def test_pi_heats_when_indoor_below_target():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    result = pi.compute(
        target_temp=21.0, indoor_temp=19.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=8.0, ki=0.0,
    )
    assert result.offset < 0
    assert result.error == 2.0


def test_pi_zero_output_at_target():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    result = pi.compute(
        target_temp=21.0, indoor_temp=21.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=8.0, ki=0.0,
    )
    assert result.offset == 0.0
    assert result.error == 0.0


def test_pi_integral_builds_over_time():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    pi.compute(
        target_temp=21.0, indoor_temp=20.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=0.0, ki=1.0,
    )
    assert pi._integral > 0.0


def test_pi_integral_frozen_during_braking():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    pi.compute(
        target_temp=21.0, indoor_temp=19.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=0.0, ki=1.0,
        braking_active=False,
    )
    integral_before = pi._integral
    assert integral_before > 0.0

    pi.compute(
        target_temp=21.0, indoor_temp=19.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t + timedelta(minutes=10),
        kp=0.0, ki=1.0,
        braking_active=True, brake_behavior="freeze",
    )
    assert pi._integral == integral_before


def test_pi_integral_decays_during_braking_with_decay_mode():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    pi.compute(
        target_temp=21.0, indoor_temp=19.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=0.0, ki=1.0,
        braking_active=False,
    )
    integral_before = pi._integral

    pi.compute(
        target_temp=21.0, indoor_temp=19.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t + timedelta(minutes=10),
        kp=0.0, ki=1.0,
        braking_active=True, brake_behavior="decay", decay_per_minute_on_brake=0.9,
    )
    assert pi._integral < integral_before


def test_pi_output_clamped_to_output_clamp():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    result = pi.compute(
        target_temp=30.0, indoor_temp=0.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=100.0, ki=0.0,
        output_clamp=20.0,
    )
    assert abs(result.offset) <= 20.0


def test_pi_reset_clears_state():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    pi.compute(
        target_temp=21.0, indoor_temp=18.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, ki=1.0,
    )
    assert pi._integral != 0.0
    pi.reset(t)
    assert pi._integral == 0.0
    assert pi._last_error == 0.0
    assert pi._last_time == t


# ═════════════════════════════════════════════════════════════════════════════
# 9. Safe mode + available-property
# ═════════════════════════════════════════════════════════════════════════════

def test_safe_mode_with_outdoor_sets_passthrough():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor, MODE_SAFE
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    t = now_utc()
    s._enter_safe_mode("Testorsak", outdoor=5.0, now=t)
    assert s._state == 5.0
    assert s._attributes["mode"] == MODE_SAFE
    assert s.available is True
    assert "Testorsak" in s._attributes["status"]


def test_safe_mode_without_outdoor_sets_unavailable():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor, MODE_SAFE
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    t = now_utc()
    s._enter_safe_mode("Ingen utesensor", outdoor=None, now=t)
    assert s._state is None
    assert s.available is False
    assert s._attributes["mode"] == MODE_SAFE


def test_safe_mode_resets_pi_and_brake():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    t = now_utc()
    s._brake_ramp = 0.8
    s._brake_last_t = t
    s._brake_last_expensive_t = t
    s._enter_safe_mode("Test", outdoor=5.0, now=t)
    assert s._brake_ramp == 0.0
    assert s._brake_last_t is None
    assert s._brake_last_expensive_t is None
    assert s._pi._integral == 0.0


def test_available_false_when_state_none():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = None
    assert s.available is False


def test_available_true_when_state_is_float():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0
    assert s.available is True


# ═════════════════════════════════════════════════════════════════════════════
# 10. Holiday sentinel-år — FIX: korrekt parse_datetime i stubs
# ═════════════════════════════════════════════════════════════════════════════

def test_holiday_sentinel_1970_returns_none():
    from custom_components.pumpsteer.holiday import _get_datetime
    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": "1970-01-01 00:00:00"})
    result = _get_datetime(hass, "input_datetime.pumpsteer_holiday_start")
    assert result is None


def test_holiday_unknown_state_returns_none():
    from custom_components.pumpsteer.holiday import _get_datetime
    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": "unknown"})
    result = _get_datetime(hass, "input_datetime.pumpsteer_holiday_start")
    assert result is None


def test_holiday_empty_state_returns_none():
    from custom_components.pumpsteer.holiday import _get_datetime
    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": ""})
    result = _get_datetime(hass, "input_datetime.pumpsteer_holiday_start")
    assert result is None


def test_holiday_valid_date_returns_datetime():
    """FIX: fungerar nu med uppdaterad parse_datetime i ha_test_stubs."""
    from custom_components.pumpsteer.holiday import _get_datetime
    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": "2025-07-01 10:00:00"})
    result = _get_datetime(hass, "input_datetime.pumpsteer_holiday_start")
    assert result is not None
    assert result.year == 2025
    assert result.month == 7
    assert result.day == 1


def test_holiday_missing_entity_returns_none():
    from custom_components.pumpsteer.holiday import _get_datetime
    hass = DummyHass({})
    result = _get_datetime(hass, "input_datetime.pumpsteer_holiday_start")
    assert result is None
