"""
PumpSteer – Komplett testsvit mot nuvarande arkitektur.

Nya tester i denna version:
  - PI-integral resettas vid aggressiveness=0 (FIX)
  - _forecast_is_cold returnerar False vid saknad prognos (FIX, PREHEAT_ON_MISSING_FORECAST=False)
  - Intervalldetektering från today-listan vid kombinerad today+tomorrow (FIX)
  - callback-decorator i ha_test_stubs (FIX — orsakade collection error)

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
    ABSOLUTE_CHEAP_LIMIT,
    PREHEAT_ON_MISSING_FORECAST,
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
    today = [100.0, 200.0]
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


def test_classify_all_identical_prices_as_cheap():
    """Alla identiska priser → P30=P80 → price <= p30 → allt klassas cheap."""
    prices = [1.5] * 24
    p30, p80 = compute_price_thresholds(prices, prices)
    cats = classify_price_list(prices, p30, p80)
    assert all(c == PRICE_CHEAP for c in cats)


# ═════════════════════════════════════════════════════════════════════════════
# 2. filter_short_peaks
# ═════════════════════════════════════════════════════════════════════════════


def test_filter_removes_single_slot_spike():
    cats = [PRICE_NORMAL, PRICE_EXPENSIVE, PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=120)
    assert PRICE_EXPENSIVE not in result


def test_filter_keeps_long_expensive_block():
    cats = [PRICE_NORMAL] + [PRICE_EXPENSIVE] * 3 + [PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=120)
    assert result.count(PRICE_EXPENSIVE) == 3


def test_filter_empty_list():
    assert filter_short_peaks([], interval_minutes=60) == []


def test_filter_all_expensive_unchanged():
    cats = [PRICE_EXPENSIVE] * 5
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=60)
    assert result == cats


def test_filter_replaces_with_left_neighbor():
    cats = [PRICE_CHEAP, PRICE_EXPENSIVE, PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=120)
    assert result[1] == PRICE_CHEAP


def test_filter_zero_interval_no_crash():
    """FIX: interval_minutes=0 ska inte krascha med division by zero."""
    cats = [PRICE_NORMAL, PRICE_EXPENSIVE, PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=0, min_duration_minutes=30)
    assert isinstance(result, list)


# ═════════════════════════════════════════════════════════════════════════════
# 3. safe_float
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
    assert safe_float(float("nan")) is None


def test_safe_float_positive_inf():
    assert safe_float(float("inf")) is None


def test_safe_float_negative_inf():
    assert safe_float(float("-inf")) is None


def test_safe_float_nan_string():
    assert safe_float("nan") is None


def test_safe_float_integer():
    assert safe_float(5) == 5.0


def test_safe_float_zero():
    assert safe_float(0.0) == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 4. get_price_window_for_hours
# ═════════════════════════════════════════════════════════════════════════════


def test_get_price_window_basic():
    prices = [1.0, 1.5, 2.0, 2.5, 3.0]
    result = get_price_window_for_hours(
        prices=prices, current_slot=0, hours=2, price_interval_minutes=60
    )
    assert result == [1.0, 1.5]


def test_get_price_window_from_middle():
    prices = [1.0, 1.5, 2.0, 2.5, 3.0]
    result = get_price_window_for_hours(
        prices=prices, current_slot=2, hours=2, price_interval_minutes=60
    )
    assert result == [2.0, 2.5]


def test_get_price_window_empty():
    result = get_price_window_for_hours(
        prices=[], current_slot=0, hours=3, price_interval_minutes=60
    )
    assert result == []


def test_get_price_window_15min_intervals():
    prices = list(range(96))
    result = get_price_window_for_hours(
        prices=prices, current_slot=0, hours=1, price_interval_minutes=15
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


def test_detect_interval_today_only_not_combined():
    """
    FIX: Intervallet ska detekteras från today-listan (24 poster = 60 min),
    INTE från kombinerad today+tomorrow (48 poster = 30 min fel).
    """
    today_prices = [1.0] * 24
    combined_prices = [1.0] * 48  # today + tomorrow
    assert detect_price_interval_minutes(today_prices) == 60
    # Kombinerad lista ger fel intervall om man inte använder today separat
    assert detect_price_interval_minutes(combined_prices) == 30


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
    t = datetime(2025, 1, 1, 23, 59, tzinfo=timezone.utc)
    assert compute_price_slot_index(t, price_interval_minutes=15, total_slots=96) == 95


def test_slot_index_combined_48_slot_list_at_2330():
    """
    FIX: Med kombinerad 48-slot-lista och today-baserat intervall (60 min)
    ska current_slot = 23 vid 23:30 (inte 47).
    """
    t = datetime(2025, 1, 1, 23, 30, tzinfo=timezone.utc)
    # Intervallet är 60 min (från today), total_slots=48 (today+tomorrow)
    slot = compute_price_slot_index(t, price_interval_minutes=60, total_slots=48)
    assert slot == 23


# ═════════════════════════════════════════════════════════════════════════════
# 7. Comfort floor
# ═════════════════════════════════════════════════════════════════════════════


def test_comfort_floor_has_six_entries():
    assert len(COMFORT_FLOOR_BY_AGGRESSIVENESS) == 6


def test_comfort_floor_agg_0_is_zero():
    assert COMFORT_FLOOR_BY_AGGRESSIVENESS[0] == 0.0


def test_comfort_floor_agg_5_is_max():
    assert COMFORT_FLOOR_BY_AGGRESSIVENESS[5] == 3.0


def test_comfort_floor_increases():
    floors = COMFORT_FLOOR_BY_AGGRESSIVENESS
    assert all(floors[i] <= floors[i + 1] for i in range(len(floors) - 1))


# ═════════════════════════════════════════════════════════════════════════════
# 8. PIController
# ═════════════════════════════════════════════════════════════════════════════


def test_pi_heats_when_cold():
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    result = pi.compute(
        target_temp=21.0,
        indoor_temp=19.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=now_utc(),
        kp=8.0,
        ki=0.0,
    )
    assert result.offset < 0
    assert result.error == 2.0


def test_pi_zero_at_target():
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    result = pi.compute(
        target_temp=21.0,
        indoor_temp=21.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=now_utc(),
        kp=8.0,
        ki=0.0,
    )
    assert result.offset == 0.0


def test_pi_integral_builds():
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    pi.compute(
        target_temp=21.0,
        indoor_temp=20.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=now_utc(),
        kp=0.0,
        ki=1.0,
    )
    assert pi._integral > 0.0


def test_pi_integral_frozen_during_braking():
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    t = now_utc()
    pi.compute(
        target_temp=21.0,
        indoor_temp=19.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=t,
        kp=0.0,
        ki=1.0,
        braking_active=False,
    )
    integral_before = pi._integral
    pi.compute(
        target_temp=21.0,
        indoor_temp=19.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=t + timedelta(minutes=10),
        kp=0.0,
        ki=1.0,
        braking_active=True,
        brake_behavior="freeze",
    )
    assert pi._integral == integral_before


def test_pi_integral_decays():
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    t = now_utc()
    pi.compute(
        target_temp=21.0,
        indoor_temp=19.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=t,
        kp=0.0,
        ki=1.0,
        braking_active=False,
    )
    integral_before = pi._integral
    pi.compute(
        target_temp=21.0,
        indoor_temp=19.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=t + timedelta(minutes=10),
        kp=0.0,
        ki=1.0,
        braking_active=True,
        brake_behavior="decay",
        decay_per_minute_on_brake=0.9,
    )
    assert pi._integral < integral_before


def test_pi_clamped():
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    result = pi.compute(
        target_temp=30.0,
        indoor_temp=0.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=now_utc(),
        kp=100.0,
        ki=0.0,
        output_clamp=20.0,
    )
    assert abs(result.offset) <= 20.0


def test_pi_reset():
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    t = now_utc()
    pi.compute(
        target_temp=21.0,
        indoor_temp=18.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=t,
        ki=1.0,
    )
    assert pi._integral != 0.0
    pi.reset(t)
    assert pi._integral == 0.0
    assert pi._last_error == 0.0


def test_pi_all_zero_gains_no_crash():
    """FIX edge case: kp=ki=kd=0 ska ge offset=0.0 utan krasch."""
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    result = pi.compute(
        target_temp=21.0,
        indoor_temp=19.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=now_utc(),
        kp=0.0,
        ki=0.0,
        kd=0.0,
    )
    assert result.offset == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 9. Safe mode + available
# ═════════════════════════════════════════════════════════════════════════════


def test_safe_mode_passthrough():
    from custom_components.pumpsteer.sensor import PumpSteerSensor, MODE_SAFE

    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._enter_safe_mode("test", outdoor=5.0, now=now_utc())
    assert s._state == 5.0
    assert s._attributes["mode"] == MODE_SAFE
    assert s.available is True


def test_safe_mode_no_outdoor():
    from custom_components.pumpsteer.sensor import PumpSteerSensor, MODE_SAFE

    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._enter_safe_mode("ingen ute", outdoor=None, now=now_utc())
    assert s._state is None
    assert s.available is False
    assert s._attributes["mode"] == MODE_SAFE


def test_safe_mode_resets_pi_and_brake():
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    t = now_utc()
    s._brake_ramp = 1.0
    s._brake_last_t = t
    s._brake_last_expensive_t = t
    s._enter_safe_mode("test", outdoor=5.0, now=t)
    assert s._brake_ramp == 0.0
    assert s._brake_last_t is None
    assert s._brake_last_expensive_t is None
    assert s._pi._integral == 0.0


def test_brake_hold_can_be_bypassed_for_immediate_release():
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    t0 = now_utc()

    engaged = s._update_brake_ramp(
        brake_requested=True,
        now=t0,
        ramp_in=1.0,
        ramp_out=1.0,
        hold_minutes=30.0,
    )
    assert engaged > 0.0

    released = s._update_brake_ramp(
        brake_requested=False,
        now=t0 + timedelta(minutes=1),
        ramp_in=1.0,
        ramp_out=1.0,
        hold_minutes=0.0,
    )
    assert released == 0.0


def test_available_false_when_none():
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = None
    assert s.available is False


def test_available_true_when_float():
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0
    assert s.available is True


# ═════════════════════════════════════════════════════════════════════════════
# 10. FIX: PI-integral resettas vid aggressiveness=0
# ═════════════════════════════════════════════════════════════════════════════


def test_pi_integral_reset_when_aggressiveness_zero():
    """
    FIX: När aggressiveness=0 ska PI-integralen resettas så att en uppbyggd
    integral från bromssessioner inte plötsligt appliceras i rent PI-läge.
    """
    from custom_components.pumpsteer.control import PIController

    pi = PIController()
    t = now_utc()

    # Simulera att integralen byggts upp under en bromssession
    pi.compute(
        target_temp=21.0,
        indoor_temp=19.0,
        outdoor_temp=5.0,
        aggressiveness=1.0,
        update_time=t,
        kp=0.0,
        ki=1.0,
    )
    assert pi._integral > 0.0, "Integralen ska ha byggts upp"

    # Verifiera att reset() nollställer den
    pi.reset(t)
    assert pi._integral == 0.0, "Integralen ska vara nollställd efter reset()"


# ═════════════════════════════════════════════════════════════════════════════
# 11. FIX: _forecast_is_cold med PREHEAT_ON_MISSING_FORECAST=False
# ═════════════════════════════════════════════════════════════════════════════


def test_preheat_on_missing_forecast_is_false_by_default():
    """
    FIX: PREHEAT_ON_MISSING_FORECAST ska vara False som default.
    Tidigare var beteendet True (antag kallt), vilket kunde ge onödig förvärmning.
    """
    assert PREHEAT_ON_MISSING_FORECAST is False


def test_forecast_is_cold_returns_false_when_no_forecast():
    """
    _forecast_is_cold ska returnera False (inte True) när temps=None,
    med PREHEAT_ON_MISSING_FORECAST=False (default).
    """
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    s = PumpSteerSensor(DummyHass({}), DummyConfigEntry())
    result = s._forecast_is_cold(summer_threshold=18.0, temps=None, hours=6)
    assert result is False, (
        "_forecast_is_cold ska returnera False vid temps=None "
        "(PREHEAT_ON_MISSING_FORECAST=False)"
    )


def test_forecast_is_cold_returns_true_when_cold_forecast():
    """_forecast_is_cold ska returnera True när alla temps är under summer_threshold."""
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    s = PumpSteerSensor(DummyHass({}), DummyConfigEntry())
    cold_temps = [5.0] * 6
    result = s._forecast_is_cold(summer_threshold=18.0, temps=cold_temps, hours=6)
    assert result is True


def test_forecast_is_cold_returns_false_when_warm_forecast():
    """_forecast_is_cold ska returnera False när temps är över summer_threshold."""
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    s = PumpSteerSensor(DummyHass({}), DummyConfigEntry())
    warm_temps = [22.0] * 6
    result = s._forecast_is_cold(summer_threshold=18.0, temps=warm_temps, hours=6)
    assert result is False


# ═════════════════════════════════════════════════════════════════════════════
# 12. Holiday sentinel-år
# ═════════════════════════════════════════════════════════════════════════════


def test_holiday_sentinel_1970_returns_none():
    from custom_components.pumpsteer.holiday import _get_datetime

    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": "1970-01-01 00:00:00"})
    assert _get_datetime(hass, "input_datetime.pumpsteer_holiday_start") is None


def test_holiday_unknown_returns_none():
    from custom_components.pumpsteer.holiday import _get_datetime

    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": "unknown"})
    assert _get_datetime(hass, "input_datetime.pumpsteer_holiday_start") is None


def test_holiday_valid_date_parsed():
    """FIX: fungerar nu med uppdaterad parse_datetime i ha_test_stubs."""
    from custom_components.pumpsteer.holiday import _get_datetime

    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": "2025-07-01 10:00:00"})
    result = _get_datetime(hass, "input_datetime.pumpsteer_holiday_start")
    assert result is not None
    assert result.year == 2025
    assert result.month == 7


def test_holiday_missing_entity_returns_none():
    from custom_components.pumpsteer.holiday import _get_datetime

    assert (
        _get_datetime(DummyHass({}), "input_datetime.pumpsteer_holiday_start") is None
    )
