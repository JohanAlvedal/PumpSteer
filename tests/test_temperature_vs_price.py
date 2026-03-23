"""
PumpSteer – Testsvit mot nuvarande arkitektur (PI-kontroller + state machine).

Kör med:
    pytest tests/ -v

Täcker:
    - Prisklassificering (classify_price, compute_thresholds, filter_short_peaks)
    - safe_float med edge cases (nan, inf, unavailable)
    - Comfort floor per aggressiveness-nivå
    - PIController: uppvärmning, fryst integral vid bromsning, reset
    - Safe mode: sensor unavailable när sensorer/prisdata saknas
    - Holiday sentinel-år
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401 — måste importeras innan HA-moduler

from custom_components.pumpsteer.electricity_price import (
    classify_price,
    classify_price_list,
    compute_price_thresholds,
    filter_short_peaks,
    PRICE_CHEAP,
    PRICE_NORMAL,
    PRICE_EXPENSIVE,
)
from custom_components.pumpsteer.utils import safe_float
from custom_components.pumpsteer.settings import (
    COMFORT_FLOOR_BY_AGGRESSIVENESS,
    BRAKE_DELTA_C,
    MIN_FAKE_TEMP,
    MAX_FAKE_TEMP,
    ABSOLUTE_CHEAP_LIMIT,
)


# ── Gemensamma test-hjälpklasser ──────────────────────────────────────────────

class DummyState:
    def __init__(self, state):
        self.state = state
        self.attributes = {}


class DummyStates:
    def __init__(self, mapping=None):
        self._m = mapping or {}

    def get(self, entity_id):
        v = self._m.get(entity_id)
        return DummyState(v) if v is not None else None


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
    today   = [100.0, 200.0]   # ska ignoreras — history är tillräcklig
    p30, p80 = compute_price_thresholds(history, today)
    assert 0 < p30 < p80
    # P80 ska inte vara i närheten av today-värdena
    assert p80 < 50.0


def test_compute_thresholds_falls_back_to_today():
    p30, p80 = compute_price_thresholds([], [1.0, 2.0, 3.0, 4.0, 5.0])
    assert p30 < p80


def test_compute_thresholds_empty_returns_zero():
    """Ska inte krascha — returnerar (0.0, 0.0)."""
    p30, p80 = compute_price_thresholds([], [])
    assert p30 == 0.0
    assert p80 == 0.0


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
    """En kort spike ska ersättas av sin vänstra granne."""
    cats   = [PRICE_CHEAP, PRICE_EXPENSIVE, PRICE_NORMAL]
    result = filter_short_peaks(cats, interval_minutes=60, min_duration_minutes=120)
    assert result[1] == PRICE_CHEAP


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


def test_safe_float_integer_input():
    assert safe_float(5) == 5.0


# ═════════════════════════════════════════════════════════════════════════════
# 4. Comfort floor per aggressiveness
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
# 5. PIController
# ═════════════════════════════════════════════════════════════════════════════

def test_pi_heats_when_indoor_below_target():
    from custom_components.pumpsteer.control import PIController
    pi = PIController()
    t  = now_utc()
    result = pi.compute(
        target_temp=21.0, indoor_temp=19.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=8.0, ki=0.0,
    )
    # error = 2.0 → P = 16.0 → raw_output = -16.0 → clamped negativt
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

    # Bygg upp integral
    pi.compute(
        target_temp=21.0, indoor_temp=19.0, outdoor_temp=5.0,
        aggressiveness=1.0, update_time=t, kp=0.0, ki=1.0,
        braking_active=False,
    )
    integral_before = pi._integral
    assert integral_before > 0.0

    # Kör med braking_active=True och brake_behavior="freeze"
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
# 6. Safe mode — sensor unavailable vid saknade data
# ═════════════════════════════════════════════════════════════════════════════

def test_safe_mode_entered_when_no_prices():
    """Om _get_prices returnerar tom lista ska sensorn gå i safe mode."""
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor, MODE_SAFE

    hass = DummyHass({
        "sensor.indoor":  "21.0",
        "sensor.outdoor": "5.0",
    })
    entry = DummyConfigEntry()
    entry.data = {
        "indoor_temp_entity":       "sensor.indoor",
        "real_outdoor_entity":      "sensor.outdoor",
        "electricity_price_entity": "sensor.price",
    }

    s = PumpSteerSensor(hass, entry)
    t = now_utc()

    # Simulera safe mode direkt via metoden
    s._enter_safe_mode("Testorsak: ingen prisdata", outdoor=5.0, now=t)

    assert s._state == 5.0                           # passthrough
    assert s._attributes["mode"] == MODE_SAFE
    assert s.available is True                       # FIX 1: available = state is not None
    assert "Testorsak" in s._attributes["status"]


def test_safe_mode_unavailable_when_no_outdoor():
    """Om utesensorn saknas ska sensorn vara unavailable (state=None)."""
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor, MODE_SAFE

    hass  = DummyHass()
    entry = DummyConfigEntry()
    s     = PumpSteerSensor(hass, entry)
    t     = now_utc()

    s._enter_safe_mode("Ingen utesensor", outdoor=None, now=t)

    assert s._state is None
    assert s.available is False                      # FIX 1: None → not available
    assert s._attributes["mode"] == MODE_SAFE


def test_safe_mode_resets_pi_and_brake():
    """Safe mode ska nollställa PI-integralen och bromsen."""
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor

    hass  = DummyHass()
    entry = DummyConfigEntry()
    s     = PumpSteerSensor(hass, entry)
    t     = now_utc()

    # Simulera att broms och integral har byggts upp
    s._brake_ramp = 0.8
    s._brake_last_t = t
    s._brake_last_expensive_t = t

    s._enter_safe_mode("Test", outdoor=5.0, now=t)

    assert s._brake_ramp == 0.0
    assert s._brake_last_t is None
    assert s._brake_last_expensive_t is None
    assert s._pi._integral == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 7. available-property (FIX 1)
# ═════════════════════════════════════════════════════════════════════════════

def test_available_false_when_state_is_none():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = None
    assert s.available is False


def test_available_true_when_state_is_float():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0
    assert s.available is True


def test_available_true_after_safe_mode_with_outdoor():
    from custom_components.pumpsteer.sensor.sensor import PumpSteerSensor
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._enter_safe_mode("test", outdoor=3.0, now=now_utc())
    assert s.available is True


# ═════════════════════════════════════════════════════════════════════════════
# 8. Holiday sentinel-år
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


def test_holiday_valid_date_returns_datetime():
    from custom_components.pumpsteer.holiday import _get_datetime
    hass = DummyHass({"input_datetime.pumpsteer_holiday_start": "2025-07-01 10:00:00"})
    result = _get_datetime(hass, "input_datetime.pumpsteer_holiday_start")
    assert result is not None
    assert result.year == 2025
