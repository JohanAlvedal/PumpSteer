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
        _LOGGER.debug(
            "weather.get_forecasts failed for %s: %s", weather_entity_id, err
        )
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