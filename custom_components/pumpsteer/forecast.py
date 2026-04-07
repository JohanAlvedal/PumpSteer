"""
forecast.py

This module provides two separate responsibilities:

1. Forecast normalization for PumpSteer utility/control support
2. Thermal outlook analysis for diagnostics and observability

IMPORTANT:
In PumpSteer 2.1.0, ThermalOutlook is diagnostic only.
It does not directly influence active control decisions.

The main control loop continues to use simpler forecast gating
such as _forecast_is_cold() and _should_precool().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant

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

    This structure provides diagnostic insight into upcoming thermal conditions,
    such as cold periods, warming trends, and precool risk.

    In PumpSteer 2.1.0, this is used for observability and visualization only
    (for example via ThermalOutlookSensor) and does NOT directly influence
    control decisions.

    The active control loop continues to use simpler forecast gating
    such as _forecast_is_cold().
    """

    # Raw values
    night_min_temp: Optional[float]  # Lowest temperature in 22:00–06:00 window
    day_max_temp: Optional[float]  # Highest temperature in 06:00–22:00 window
    hours_below_threshold: int  # Hours below summer_threshold in analysis window
    effective_temp_now: Optional[
        float
    ]  # Wind-chill-adjusted temperature for nearest point

    # Trends
    warming_trend: bool  # Temperature rising in the near horizon
    cooling_trend: bool  # Temperature falling in the near horizon

    # Risk signal
    precool_risk: bool  # Warm period ahead that may reduce preheat value

    # Diagnostic summary outputs
    preheat_worthwhile: bool  # Diagnostic estimate only in 2.1.0
    preheat_strength: float  # Diagnostic estimate only in 2.1.0


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
    Calculate a simplified wind chill estimate.

    Valid below approximately 10°C and for wind speeds above 1.3 m/s.
    Outside these bounds, the raw outdoor temperature is returned unchanged.
    """
    if temp_c >= 10.0 or wind_ms < 1.3:
        return temp_c
    v016 = wind_ms**0.16
    return 13.12 + 0.6215 * temp_c - 11.37 * v016 + 0.3965 * temp_c * v016


async def _async_extract_weather_points(
    hass: HomeAssistant,
    weather_entity_id: str,
    horizon_hours: int,
) -> dict[datetime, ForecastPoint]:
    """Read hourly weather forecast via weather.get_forecasts service call."""

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
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    end_utc = now_utc + timedelta(hours=horizon_hours)
    result: dict[datetime, ForecastPoint] = {}

    for entry in forecast:
        if not isinstance(entry, dict):
            continue

        ts = _parse_datetime(entry.get("datetime"))
        if ts is None:
            continue

        ts = _round_to_hour(ts)

        if ts < current_hour:
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

    Expected sources include:
    - raw_today / raw_tomorrow style lists
    - forecast-like price lists in entity attributes
    """
    state = hass.states.get(price_entity_id)
    if state is None:
        _LOGGER.debug("Price entity not found: %s", price_entity_id)
        return {}

    now_utc = dt_util.utcnow()
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    end_utc = now_utc + timedelta(hours=horizon_hours)

    candidates: list[dict[str, Any]] = []

    for attr_name in ("raw_today", "raw_tomorrow", "prices", "forecast"):
        attr = state.attributes.get(attr_name)
        if isinstance(attr, list):
            candidates.extend(item for item in attr if isinstance(item, dict))

    result: dict[datetime, float] = {}

    for entry in candidates:
        ts = _extract_price_timestamp(entry)
        if ts is None:
            continue

        if ts < current_hour:
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
    Build a normalized hourly forecast for PumpSteer utility and diagnostics.

    This function merges:
    - future weather forecast from a weather entity
    - future electricity prices from a price entity

    In 2.1.0, this supports both:
    - simple control-facing forecast helpers
    - richer diagnostic analysis such as ThermalOutlook
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
    precool_margin: float = 3.0,
    trend_hours: int = 6,
) -> ThermalOutlook:
    """
    Analyze a ForecastPoint list and return a ThermalOutlook.

    This function produces a richer thermal interpretation of the forecast,
    including trends, cold duration, effective temperature, and precool risk.

    In PumpSteer 2.1.0, this analysis is intended for diagnostics and future
    control improvements. It is NOT part of the active control decision path.

    The main control loop still relies on simpler forecast signals.
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

    # Split into night (22–06) and day (06–22) based on forecast timestamp hour.
    night_temps: list[float] = []
    day_temps: list[float] = []
    for point in points:
        if point.outdoor_temp is None:
            continue
        hour = point.timestamp.hour
        if hour >= 22 or hour < 6:
            night_temps.append(point.outdoor_temp)
        else:
            day_temps.append(point.outdoor_temp)

    night_min = min(night_temps) if night_temps else None
    day_max = max(day_temps) if day_temps else None

    # Count hours below the threshold in the provided analysis window.
    hours_cold = sum(
        1
        for point in points
        if point.outdoor_temp is not None and point.outdoor_temp < summer_threshold
    )

    # Wind-chill-adjusted temperature for the nearest forecast point.
    eff_temp: Optional[float] = None
    if points[0].outdoor_temp is not None:
        wind = points[0].wind_speed or 0.0
        eff_temp = _wind_chill(points[0].outdoor_temp, wind)

    # Trend analysis based on the first trend_hours forecast points.
    trend_temps = [
        point.outdoor_temp
        for point in points[:trend_hours]
        if point.outdoor_temp is not None
    ]
    warming = False
    cooling = False
    if len(trend_temps) >= 4:
        mid = len(trend_temps) // 2
        early_avg = sum(trend_temps[:mid]) / mid
        late_avg = sum(trend_temps[mid:]) / (len(trend_temps) - mid)
        warming = late_avg > early_avg + 1.0
        cooling = late_avg < early_avg - 1.0

    # Warm daytime period ahead may reduce the value of preheating.
    precool_risk = day_max is not None and day_max >= summer_threshold + precool_margin

    # Diagnostic estimate only in 2.1.0.
    preheat_worthwhile = (
        hours_cold >= 3
        and not warming
        and not precool_risk
        and (day_max is None or day_max < summer_threshold - 2.0)
    )

    # Diagnostic estimate only in 2.1.0.
    preheat_strength = 0.0
    if preheat_worthwhile and night_min is not None:
        delta = summer_threshold - night_min
        preheat_strength = min(1.0, max(0.0, delta / 15.0))

    # NOTE:
    # ThermalOutlook is diagnostic only in 2.1.0.
    # It must not be used to directly control preheat/brake decisions.
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
