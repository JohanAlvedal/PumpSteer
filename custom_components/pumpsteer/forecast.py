from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, Optional

from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)


@dataclass
class ForecastPoint:
    """Normalized future data for one planning step."""

    timestamp: datetime
    price: Optional[float]
    outdoor_temp: Optional[float]
    wind_speed: Optional[float]
    wind_gust_speed: Optional[float]
    cloud_coverage: Optional[float] = None
    precipitation: Optional[float] = None
    humidity: Optional[float] = None
    source_price: str = "unknown"
    source_weather: str = "unknown"


@dataclass
class ThermalOutlook:
    """
    Summarized thermal analysis based on upcoming weather and prices.
    Used as decision support for preheat/precool — replaces binary _forecast_is_cold().
    Produced by analyze_thermal_outlook(), consumed by sensor.py (block 5b) and
    ThermalOutlookSensor for visualization.
    """

    # Raw values
    night_min_temp: Optional[float]      # lowest temp 22:00–06:00
    day_max_temp: Optional[float]        # highest temp 06:00–22:00
    hours_below_threshold: int           # hours below summer_threshold (24h window)
    effective_temp_now: Optional[float]  # wind-chill-adjusted current temp

    # Trends (next trend_hours hours)
    warming_trend: bool   # temp rising → warm day ahead, hold back preheat
    cooling_trend: bool   # temp falling → cold night ahead, preheat motivated

    # Risk signal
    precool_risk: bool    # warm period ahead (day_max >= summer_threshold + margin)

    # Decision outputs (computed)
    preheat_worthwhile: bool  # is preheat justified given the full picture?
    preheat_strength: float   # 0.0–1.0, scales PREHEAT_BOOST_C


def _as_float(value: Any) -> Optional[float]:
    """Convert a value to float when possible."""
    try:
        if value in (None, "", "unknown", "unavailable", "None"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime and normalize to aware UTC datetime."""
    if not value:
        return None

    if isinstance(value, datetime):
        dt_value = value
    else:
        dt_value = dt_util.parse_datetime(str(value))

    if dt_value is None:
        return None

    if dt_value.tzinfo is None:
        dt_value = dt_util.as_utc(dt_value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE))
    else:
        dt_value = dt_util.as_utc(dt_value)

    return dt_value


def _round_to_hour(dt_value: datetime) -> datetime:
    """Round down datetime to whole hour in UTC."""
    return dt_value.replace(minute=0, second=0, microsecond=0)


def _wind_chill(temp_c: float, wind_ms: float) -> float:
    """
    JAG wind chill index (simplified).
    Valid below ~10°C and wind > 1.3 m/s.
    Outside these bounds, raw temperature is returned unchanged.
    """
    if temp_c >= 10.0 or wind_ms < 1.3:
        return temp_c
    v016 = wind_ms ** 0.16
    return 13.12 + 0.6215 * temp_c - 11.37 * v016 + 0.3965 * temp_c * v016


async def _async_extract_weather_points(
    hass: HomeAssistant,
    weather_entity_id: str,
    horizon_hours: int,
) -> dict[datetime, ForecastPoint]:
    """Read hourly weather forecast via weather.get_forecasts service call (HA 2024.x+)."""

    try:
        response = await hass.services.async_call(
            "weather",
            "get_forecasts",
            {"type": "hourly"},
            target={"entity_id": weather_entity_id},
            blocking=True,
            return_response=True,
        )
    except Exception as err:
        _LOGGER.debug("weather.get_forecasts failed for %s: %s", weather_entity_id, err)
        return {}

    if not isinstance(response, dict):
        _LOGGER.debug(
            "weather.get_forecasts returned unexpected type for %s: %s",
            weather_entity_id,
            type(response),
        )
        return {}

    entity_data = response.get(weather_entity_id, {})
    forecast = entity_data.get("forecast") if isinstance(entity_data, dict) else None

    if not isinstance(forecast, list):
        _LOGGER.debug(
            "No forecast list in weather.get_forecasts response for %s",
            weather_entity_id,
        )
        return {}

    now_utc = dt_util.utcnow()
    end_utc = now_utc + timedelta(hours=horizon_hours)
    result: dict[datetime, ForecastPoint] = {}

    for entry in forecast:
        if not isinstance(entry, dict):
            continue

        ts = _parse_datetime(entry.get("datetime"))
        if ts is None:
            continue

        ts = _round_to_hour(ts)

        if ts < now_utc.replace(minute=0, second=0, microsecond=0):
            continue
        if ts > end_utc:
            continue

        result[ts] = ForecastPoint(
            timestamp=ts,
            price=None,
            outdoor_temp=_as_float(entry.get("temperature")),
            wind_speed=_as_float(entry.get("wind_speed")),
            wind_gust_speed=_as_float(entry.get("wind_gust_speed")),
            cloud_coverage=_as_float(entry.get("cloud_coverage")),
            precipitation=_as_float(entry.get("precipitation")),
            humidity=_as_float(entry.get("humidity")),
            source_weather=weather_entity_id,
        )

    return result


def _extract_price_value(entry: dict[str, Any]) -> Optional[float]:
    """Extract numeric price from a raw price entry."""
    for key in ("value", "price", "total", "spot", "cost"):
        if key in entry:
            value = _as_float(entry.get(key))
            if value is not None:
                return value
    return None


def _extract_price_timestamp(entry: dict[str, Any]) -> Optional[datetime]:
    """Extract timestamp from a raw price entry."""
    for key in ("start", "startsAt", "datetime", "time", "hour"):
        if key in entry:
            ts = _parse_datetime(entry.get(key))
            if ts is not None:
                return _round_to_hour(ts)
    return None


def _extract_price_points(
    hass: HomeAssistant,
    price_entity_id: str,
    horizon_hours: int,
) -> dict[datetime, float]:
    """
    Read future hourly prices from a Home Assistant price entity.

    Expected sources:
    - raw_today / raw_tomorrow style lists
    - a forecast-like list in attributes
    """
    state = hass.states.get(price_entity_id)
    if state is None:
        _LOGGER.debug("Price entity not found: %s", price_entity_id)
        return {}

    now_utc = dt_util.utcnow()
    end_utc = now_utc + timedelta(hours=horizon_hours)

    candidates: list[dict[str, Any]] = []

    for attr_name in ("raw_today", "raw_tomorrow", "prices", "forecast"):
        attr = state.attributes.get(attr_name)
        if isinstance(attr, list):
            candidates.extend([item for item in attr if isinstance(item, dict)])

    result: dict[datetime, float] = {}

    for entry in candidates:
        ts = _extract_price_timestamp(entry)
        if ts is None:
            continue

        if ts < now_utc.replace(minute=0, second=0, microsecond=0):
            continue
        if ts > end_utc:
            continue

        value = _extract_price_value(entry)
        if value is None:
            continue

        result[ts] = value

    return result


async def async_build_forecast(
    hass: HomeAssistant,
    *,
    price_entity_id: str,
    weather_entity_id: str,
    horizon_hours: int = 24,
) -> list[ForecastPoint]:
    """
    Build a normalized hourly forecast for planner usage.

    The function merges:
    - future weather forecast from a weather entity (via weather.get_forecasts)
    - future electricity prices from a price entity
    """
    weather_points = await _async_extract_weather_points(
        hass, weather_entity_id, horizon_hours
    )
    price_points = _extract_price_points(hass, price_entity_id, horizon_hours)

    all_hours = sorted(set(weather_points.keys()) | set(price_points.keys()))
    merged: list[ForecastPoint] = []

    for ts in all_hours:
        weather_point = weather_points.get(ts)

        if weather_point is not None:
            point = ForecastPoint(
                timestamp=ts,
                price=price_points.get(ts),
                outdoor_temp=weather_point.outdoor_temp,
                wind_speed=weather_point.wind_speed,
                wind_gust_speed=weather_point.wind_gust_speed,
                cloud_coverage=weather_point.cloud_coverage,
                precipitation=weather_point.precipitation,
                humidity=weather_point.humidity,
                source_price=price_entity_id if ts in price_points else "missing",
                source_weather=weather_entity_id,
            )
        else:
            point = ForecastPoint(
                timestamp=ts,
                price=price_points.get(ts),
                outdoor_temp=None,
                wind_speed=None,
                wind_gust_speed=None,
                cloud_coverage=None,
                precipitation=None,
                humidity=None,
                source_price=price_entity_id if ts in price_points else "missing",
                source_weather="missing",
            )

        merged.append(point)

    return merged


def analyze_thermal_outlook(
    points: list[ForecastPoint],
    summer_threshold: float,
    now_hour: int,
    precool_margin: float = 3.0,
    trend_hours: int = 6,
) -> ThermalOutlook:
    """
    Analyze a ForecastPoint list and return a ThermalOutlook.

    night_min_temp: lowest temp in the night window (22:00–06:00)
    day_max_temp:   highest temp in the day window  (06:00–22:00)
    warming_trend:  true if avg(temp[mid:]) > avg(temp[:mid]) + 1°C hysteresis
    cooling_trend:  true if avg(temp[mid:]) < avg(temp[:mid]) - 1°C hysteresis
    effective_temp_now: wind-chill-adjusted temp for the nearest forecast point
    preheat_worthwhile: true if cold enough for long enough AND no warm day takes over
    preheat_strength: normalized against a 15°C span below summer_threshold
    precool_risk: true if day_max >= summer_threshold + precool_margin
    """
    if not points:
        return ThermalOutlook(
            night_min_temp=None,
            day_max_temp=None,
            hours_below_threshold=0,
            effective_temp_now=None,
            warming_trend=False,
            cooling_trend=False,
            precool_risk=False,
            preheat_worthwhile=False,
            preheat_strength=0.0,
        )

    # Split into night (22–06) and day (06–22) based on timestamp hour
    night_temps: list[float] = []
    day_temps: list[float] = []
    for p in points:
        if p.outdoor_temp is None:
            continue
        h = p.timestamp.hour
        if h >= 22 or h < 6:
            night_temps.append(p.outdoor_temp)
        else:
            day_temps.append(p.outdoor_temp)

    night_min = min(night_temps) if night_temps else None
    day_max = max(day_temps) if day_temps else None

    # Count hours below threshold
    hours_cold = sum(
        1 for p in points
        if p.outdoor_temp is not None and p.outdoor_temp < summer_threshold
    )

    # Wind chill for the nearest forecast point
    eff_temp: Optional[float] = None
    if points[0].outdoor_temp is not None:
        wind = points[0].wind_speed or 0.0
        eff_temp = _wind_chill(points[0].outdoor_temp, wind)

    # Trend: compare average of first half vs second half of trend window
    trend_temps = [
        p.outdoor_temp for p in points[:trend_hours] if p.outdoor_temp is not None
    ]
    warming = False
    cooling = False
    if len(trend_temps) >= 4:
        mid = len(trend_temps) // 2
        early_avg = sum(trend_temps[:mid]) / mid
        late_avg = sum(trend_temps[mid:]) / (len(trend_temps) - mid)
        warming = late_avg > early_avg + 1.0  # 1°C hysteresis to filter noise
        cooling = late_avg < early_avg - 1.0

    # Precool risk: a warm period is coming that will heat the house naturally
    precool_risk = day_max is not None and day_max >= summer_threshold + precool_margin

    # Is preheat worthwhile?
    # Requires: cold enough (>= 3h), no warm day taking over, temp not already rising
    preheat_worthwhile = (
        hours_cold >= 3
        and not warming
        and not precool_risk
        and (day_max is None or day_max < summer_threshold - 2.0)
    )

    # Strength: how cold relative to threshold, normalized against a 15°C span
    preheat_strength = 0.0
    if preheat_worthwhile and night_min is not None:
        delta = summer_threshold - night_min
        preheat_strength = min(1.0, max(0.0, delta / 15.0))

    return ThermalOutlook(
        night_min_temp=night_min,
        day_max_temp=day_max,
        hours_below_threshold=hours_cold,
        effective_temp_now=eff_temp,
        warming_trend=warming,
        cooling_trend=cooling,
        precool_risk=precool_risk,
        preheat_worthwhile=preheat_worthwhile,
        preheat_strength=preheat_strength,
    )
