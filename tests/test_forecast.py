"""
Tests for forecast.py — ThermalOutlook analysis and wind chill calculation.

Covers:
- _wind_chill: JAG index edge cases
- analyze_thermal_outlook: all decision outputs across key scenarios
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Stub out all homeassistant dependencies before importing forecast.py
# ---------------------------------------------------------------------------

def _make_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

_ha          = _make_module("homeassistant")
_ha_util     = _make_module("homeassistant.util")
_ha_dt       = _make_module("homeassistant.util.dt")
_ha_core     = _make_module("homeassistant.core")

_ha_dt.parse_datetime    = datetime.fromisoformat   # type: ignore[attr-defined]
_ha_dt.utcnow            = lambda: datetime.now(timezone.utc)  # type: ignore[attr-defined]
_ha_dt.as_utc            = lambda dt: dt            # type: ignore[attr-defined]
_ha_dt.DEFAULT_TIME_ZONE = timezone.utc             # type: ignore[attr-defined]
_ha_core.HomeAssistant   = object                   # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Import functions under test directly from source file
# ---------------------------------------------------------------------------

import importlib.util
import pathlib

_src  = pathlib.Path(__file__).parent / "custom_components" / "pumpsteer" / "forecast.py"
_spec = importlib.util.spec_from_file_location("pumpsteer_forecast", _src)
_mod  = importlib.util.module_from_spec(_spec)
# Register the module so dataclass resolution works
sys.modules["pumpsteer_forecast"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_wind_chill             = _mod._wind_chill
analyze_thermal_outlook = _mod.analyze_thermal_outlook
ForecastPoint           = _mod.ForecastPoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

THRESHOLD = 17.5


def _utc(hour: int, day: int = 1) -> datetime:
    return datetime(2024, 1, day, hour, 0, 0, tzinfo=timezone.utc)


def _point(hour: int, temp: Optional[float], wind: float = 0.0, day: int = 1) -> ForecastPoint:
    return ForecastPoint(
        timestamp=_utc(hour, day),
        price=None,
        outdoor_temp=temp,
        wind_speed=wind,
        wind_gust_speed=None,
    )


def _cold_night_warm_day() -> list:
    """Cold night (22–06) + warm day (06–22)."""
    return [_point(h, 2.0 if (h >= 22 or h < 6) else THRESHOLD + 3.0) for h in range(24)]


def _cold_night_cold_day() -> list:
    """Cold throughout."""
    return [_point(h, 4.0) for h in range(24)]


def _warm_summer_day() -> list:
    """All temps well above threshold."""
    return [_point(h, THRESHOLD + 5.0) for h in range(24)]


def _rising_temps() -> list:
    return [_point(h, float(5 + h * 2)) for h in range(6)]


def _falling_temps() -> list:
    return [_point(h, float(20 - h * 2)) for h in range(6)]


# ===========================================================================
# _wind_chill
# ===========================================================================

class TestWindChill:
    def test_no_wind_returns_raw_temp(self):
        assert _wind_chill(5.0, 0.0) == 5.0

    def test_low_wind_returns_raw_temp(self):
        assert _wind_chill(5.0, 1.0) == 5.0

    def test_warm_temp_returns_raw_temp(self):
        assert _wind_chill(10.0, 10.0) == 10.0
        assert _wind_chill(15.0, 15.0) == 15.0

    def test_wind_chill_reduces_temp(self):
        assert _wind_chill(-5.0, 10.0) < -5.0

    def test_wind_chill_at_boundary(self):
        assert _wind_chill(9.9, 10.0) < 9.9

    def test_wind_chill_cold_strong_wind(self):
        assert _wind_chill(-10.0, 15.0) < -15.0

    def test_wind_chill_mild_temp_light_wind(self):
        # JAG formula is not monotone near the boundary — at 5°C/3 m/s the
        # perceived temp is marginally above raw. Use stronger wind or lower
        # temp to verify the cooling effect clearly.
        assert _wind_chill(5.0, 5.0) < 5.0    # 5 m/s clears the threshold
        assert _wind_chill(2.0, 3.0) < 2.0    # lower temp gives clear cooling


# ===========================================================================
# Empty input
# ===========================================================================

class TestAnalyzeEmpty:
    def test_empty_points_returns_safe_defaults(self):
        o = analyze_thermal_outlook([], THRESHOLD, now_hour=12)
        assert o.night_min_temp is None
        assert o.day_max_temp is None
        assert o.hours_below_threshold == 0
        assert o.effective_temp_now is None
        assert o.warming_trend is False
        assert o.cooling_trend is False
        assert o.precool_risk is False
        assert o.preheat_worthwhile is False
        assert o.preheat_strength == 0.0


# ===========================================================================
# Night/day split
# ===========================================================================

class TestNightDaySplit:
    def test_night_min_reflects_night_hours(self):
        o = analyze_thermal_outlook(_cold_night_warm_day(), THRESHOLD, now_hour=12)
        assert o.night_min_temp == pytest.approx(2.0)

    def test_day_max_reflects_day_hours(self):
        o = analyze_thermal_outlook(_cold_night_warm_day(), THRESHOLD, now_hour=12)
        assert o.day_max_temp == pytest.approx(THRESHOLD + 3.0)

    def test_all_cold_night_and_day(self):
        o = analyze_thermal_outlook(_cold_night_cold_day(), THRESHOLD, now_hour=12)
        assert o.night_min_temp == pytest.approx(4.0)
        assert o.day_max_temp == pytest.approx(4.0)

    def test_none_temps_excluded(self):
        points = [_point(0, None), _point(1, 3.0), _point(10, 20.0), _point(23, None)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=12)
        assert o.night_min_temp == pytest.approx(3.0)
        assert o.day_max_temp == pytest.approx(20.0)


# ===========================================================================
# hours_below_threshold
# ===========================================================================

class TestHoursBelowThreshold:
    def test_all_cold(self):
        o = analyze_thermal_outlook([_point(h, 5.0) for h in range(24)], THRESHOLD, now_hour=12)
        assert o.hours_below_threshold == 24

    def test_all_warm(self):
        o = analyze_thermal_outlook([_point(h, THRESHOLD + 1.0) for h in range(24)], THRESHOLD, now_hour=12)
        assert o.hours_below_threshold == 0

    def test_mixed(self):
        points = [_point(h, 5.0) for h in range(12)] + [_point(h + 12, THRESHOLD + 1.0) for h in range(12)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=12)
        assert o.hours_below_threshold == 12

    def test_none_temps_not_counted(self):
        points = [_point(h, None) for h in range(6)] + [_point(h + 6, 5.0) for h in range(6)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=12)
        assert o.hours_below_threshold == 6


# ===========================================================================
# Trend detection
# ===========================================================================

class TestTrendDetection:
    def test_rising_sets_warming_trend(self):
        o = analyze_thermal_outlook(_rising_temps(), THRESHOLD, now_hour=6)
        assert o.warming_trend is True
        assert o.cooling_trend is False

    def test_falling_sets_cooling_trend(self):
        o = analyze_thermal_outlook(_falling_temps(), THRESHOLD, now_hour=6)
        assert o.cooling_trend is True
        assert o.warming_trend is False

    def test_stable_no_trend(self):
        o = analyze_thermal_outlook([_point(h, 5.0) for h in range(6)], THRESHOLD, now_hour=6)
        assert o.warming_trend is False
        assert o.cooling_trend is False

    def test_small_change_within_hysteresis(self):
        # 0.1°C per step → 0.5°C total, below 1°C hysteresis
        points = [_point(h, 5.0 + h * 0.1) for h in range(6)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=6)
        assert o.warming_trend is False

    def test_too_few_points_no_trend(self):
        o = analyze_thermal_outlook([_point(h, 5.0) for h in range(3)], THRESHOLD, now_hour=6)
        assert o.warming_trend is False
        assert o.cooling_trend is False


# ===========================================================================
# precool_risk
# ===========================================================================

class TestPrecoolRisk:
    def test_warm_day_triggers_risk(self):
        o = analyze_thermal_outlook(_warm_summer_day(), THRESHOLD, now_hour=12)
        assert o.precool_risk is True

    def test_cold_day_no_risk(self):
        o = analyze_thermal_outlook(_cold_night_cold_day(), THRESHOLD, now_hour=12)
        assert o.precool_risk is False

    def test_just_below_margin_no_risk(self):
        points = [_point(h, THRESHOLD + 2.9) for h in range(8, 20)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=12, precool_margin=3.0)
        assert o.precool_risk is False

    def test_exactly_at_margin_triggers_risk(self):
        points = [_point(h, THRESHOLD + 3.0) for h in range(8, 20)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=12, precool_margin=3.0)
        assert o.precool_risk is True


# ===========================================================================
# preheat_worthwhile
# ===========================================================================

class TestPreheatWorthwhile:
    def test_cold_throughout_is_worthwhile(self):
        o = analyze_thermal_outlook(_cold_night_cold_day(), THRESHOLD, now_hour=12)
        assert o.preheat_worthwhile is True

    def test_warm_day_suppresses_preheat(self):
        o = analyze_thermal_outlook(_cold_night_warm_day(), THRESHOLD, now_hour=12)
        assert o.preheat_worthwhile is False

    def test_warming_trend_suppresses_preheat(self):
        o = analyze_thermal_outlook(_rising_temps(), THRESHOLD, now_hour=6)
        assert o.preheat_worthwhile is False

    def test_precool_risk_suppresses_preheat(self):
        o = analyze_thermal_outlook(_warm_summer_day(), THRESHOLD, now_hour=12)
        assert o.preheat_worthwhile is False

    def test_fewer_than_3_cold_hours_suppresses_preheat(self):
        points = [_point(h, 5.0) for h in range(2)] + [_point(h + 2, THRESHOLD + 1.0) for h in range(22)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=12)
        assert o.preheat_worthwhile is False

    def test_3_or_more_cold_hours_can_enable_preheat(self):
        o = analyze_thermal_outlook([_point(h, 5.0) for h in range(24)], THRESHOLD, now_hour=12)
        assert o.hours_below_threshold >= 3
        assert o.preheat_worthwhile is True


# ===========================================================================
# preheat_strength
# ===========================================================================

class TestPreheatStrength:
    def test_zero_when_not_worthwhile(self):
        o = analyze_thermal_outlook(_cold_night_warm_day(), THRESHOLD, now_hour=12)
        assert o.preheat_strength == 0.0

    def test_scales_with_coldness(self):
        cold = analyze_thermal_outlook([_point(h, 2.0) for h in range(24)], THRESHOLD, now_hour=12)
        mild = analyze_thermal_outlook([_point(h, 12.0) for h in range(24)], THRESHOLD, now_hour=12)
        assert cold.preheat_strength > mild.preheat_strength

    def test_clamped_to_1(self):
        o = analyze_thermal_outlook([_point(h, -20.0) for h in range(24)], THRESHOLD, now_hour=12)
        assert o.preheat_strength <= 1.0

    def test_never_negative(self):
        o = analyze_thermal_outlook([_point(h, THRESHOLD - 0.1) for h in range(24)], THRESHOLD, now_hour=12)
        assert o.preheat_strength >= 0.0


# ===========================================================================
# effective_temp_now
# ===========================================================================

class TestEffectiveTempNow:
    def test_no_wind_equals_raw(self):
        o = analyze_thermal_outlook([_point(h, 5.0, wind=0.0) for h in range(6)], THRESHOLD, now_hour=0)
        assert o.effective_temp_now == pytest.approx(5.0)

    def test_wind_reduces_effective_temp(self):
        o = analyze_thermal_outlook([_point(h, 5.0, wind=10.0) for h in range(6)], THRESHOLD, now_hour=0)
        assert o.effective_temp_now is not None
        assert o.effective_temp_now < 5.0

    def test_none_outdoor_gives_none_effective(self):
        points = [_point(0, None, wind=10.0)] + [_point(h, 5.0) for h in range(1, 6)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=0)
        assert o.effective_temp_now is None


# ===========================================================================
# Integration scenarios
# ===========================================================================

class TestScenarios:
    def test_spring_cold_night_sunny_day(self):
        """Cold night → warm sunny day: preheat not worthwhile."""
        points = [_point(h, 2.0 if (h >= 22 or h < 6) else 21.0) for h in range(24)]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=20)
        assert o.preheat_worthwhile is False
        assert o.night_min_temp == pytest.approx(2.0)
        assert o.day_max_temp == pytest.approx(21.0)

    def test_autumn_cold_throughout(self):
        """Cold throughout: preheat worthwhile, no precool risk."""
        o = analyze_thermal_outlook([_point(h, 5.0) for h in range(24)], THRESHOLD, now_hour=12)
        assert o.preheat_worthwhile is True
        assert o.precool_risk is False
        assert o.preheat_strength > 0.0

    def test_summer_extreme_heat(self):
        """Extreme heat: precool risk, preheat suppressed."""
        o = analyze_thermal_outlook([_point(h, 32.0) for h in range(24)], THRESHOLD, now_hour=12)
        assert o.precool_risk is True
        assert o.preheat_worthwhile is False
        assert o.preheat_strength == 0.0

    def test_windy_cold_evening(self):
        """Cold + strong wind: effective temp lower than raw."""
        o = analyze_thermal_outlook([_point(h, 3.0, wind=12.0) for h in range(6)], THRESHOLD, now_hour=0)
        assert o.effective_temp_now is not None
        assert o.effective_temp_now < 3.0

    def test_scattered_none_temps_no_crash(self):
        """Scattered None temps should not crash the function."""
        points = [
            _point(0, None), _point(1, 5.0), _point(2, None),
            _point(3, 4.0), _point(22, None), _point(23, 3.0),
        ]
        o = analyze_thermal_outlook(points, THRESHOLD, now_hour=12)
        assert o.night_min_temp == pytest.approx(3.0)
        assert o.hours_below_threshold == 3
