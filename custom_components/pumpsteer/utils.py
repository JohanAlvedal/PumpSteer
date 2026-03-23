import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.typing import StateType

from .settings import (
    MIN_REASONABLE_TEMP,
    MAX_REASONABLE_TEMP,
    MIN_REASONABLE_PRICE,
    MAX_REASONABLE_PRICE,
    PRECOOL_LOOKAHEAD,
)

_LOGGER = logging.getLogger(__name__)


def get_version() -> str:
    """Load integration version from manifest.json."""
    manifest_path = Path(__file__).resolve().parent / "manifest.json"
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("version")
        if not version:
            _LOGGER.error("Version not set in manifest.json")
            return "unknown"
        return version
    except FileNotFoundError:
        _LOGGER.error("manifest.json not found at %s", manifest_path)
        return "unknown"
    except json.JSONDecodeError as err:
        _LOGGER.error("Error decoding manifest.json: %s", err)
        return "unknown"


def safe_float(
    val: StateType,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> Optional[float]:
    """
    Safely convert value to float with optional bounds.

    Returns None for:
      - None input
      - Non-numeric strings (e.g. "unavailable", "unknown")
      - NaN and +-Inf  ← FIX: previously passed through
      - Values outside [min_val, max_val] if specified
    """
    if val is None:
        return None
    try:
        f = float(val)
        # FIX: NaN and infinity are not valid physical sensor values
        if not math.isfinite(f):
            return None
        if min_val is not None and f < min_val:
            return None
        if max_val is not None and f > max_val:
            return None
        return f
    except (TypeError, ValueError):
        return None


def get_state(
    hass: HomeAssistant,
    entity_id: str,
    default: Optional[str] = None,
) -> Optional[str]:
    """Get entity state, returning default if unavailable/unknown."""
    if not entity_id or not isinstance(entity_id, str):
        return default
    entity = hass.states.get(entity_id)
    if not entity:
        _LOGGER.debug("Entity not found: %s", entity_id)
        return default
    if entity.state in {STATE_UNAVAILABLE, STATE_UNKNOWN, "unavailable", "unknown", None}:
        return default
    return entity.state


def get_attr(
    hass: HomeAssistant,
    entity_id: str,
    attribute: str,
    default: Any = None,
) -> Any:
    """Get entity attribute."""
    if not entity_id or not attribute:
        return default
    entity = hass.states.get(entity_id)
    if not entity or not entity.attributes:
        return default
    return entity.attributes.get(attribute, default)


def safe_parse_temperature_forecast(
    csv: str,
    max_hours: Optional[int] = None,
) -> Optional[List[float]]:
    """Parse comma-separated temperature forecast string."""
    if not csv or not isinstance(csv, str):
        return None
    parts = [t.strip() for t in csv.split(",") if t.strip()]
    if not parts:
        return None
    if max_hours and max_hours > 0:
        parts = parts[:max_hours]
    temps = []
    for p in parts:
        try:
            t = float(p)
            if not math.isfinite(t):
                continue
            if MIN_REASONABLE_TEMP <= t <= MAX_REASONABLE_TEMP:
                temps.append(t)
            else:
                _LOGGER.debug("Ignoring out-of-range forecast temp: %s", t)
        except (ValueError, TypeError):
            continue
    return temps if temps else None


def detect_price_interval_minutes(prices: List[Any]) -> int:
    """Detect interval in minutes between price points."""
    if not prices:
        return 60
    count = len(prices)
    for interval in [5, 10, 15, 20, 30, 60, 120]:
        if count * interval == 1440:
            return interval
    if 1440 % count == 0:
        interval = 1440 // count
        if interval > 0:
            return interval
    estimated = max(1, math.floor(1440 / max(1, count)))
    return min([5, 10, 15, 20, 30, 60, 120], key=lambda x: abs(x - estimated))


def compute_price_slot_index(
    current_time: datetime,
    price_interval_minutes: int,
    total_slots: int,
) -> int:
    """Compute index of current price slot."""
    if total_slots <= 0:
        return 0
    interval = max(1, price_interval_minutes)
    minutes = current_time.hour * 60 + current_time.minute
    slot = minutes // interval
    return max(0, min(total_slots - 1, slot))


def get_price_window_for_hours(
    prices: List[float],
    current_slot: int,
    hours: int,
    price_interval_minutes: int,
) -> List[float]:
    """Return price slice covering the next N hours."""
    if not prices or current_slot < 0:
        return []
    interval = max(1, price_interval_minutes)
    slots = max(1, math.ceil(hours * 60 / interval))
    start = min(current_slot, len(prices) - 1)
    return prices[start: min(len(prices), start + slots)]
