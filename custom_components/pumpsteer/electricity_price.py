""electicity_price for PumpSteer."""
import logging
from datetime import timedelta
from typing import List

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import now as dt_now

from .settings import (
    ABSOLUTE_CHEAP_LIMIT,
    DEFAULT_TRAILING_HOURS,
    MIN_SAMPLES_FOR_CLASSIFICATION,
    PRICE_PERCENTILE_CHEAP,
    PRICE_PERCENTILE_EXPENSIVE,
)

_LOGGER = logging.getLogger(__name__)

PRICE_CHEAP = "cheap"
PRICE_NORMAL = "normal"
PRICE_EXPENSIVE = "expensive"


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    if p <= 0:
        return float(sorted_v[0])
    if p >= 100:
        return float(sorted_v[-1])
    k = (len(sorted_v) - 1) * (p / 100)
    lo = int(k)
    hi = min(lo + 1, len(sorted_v) - 1)
    return float(sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (k - lo))


def classify_price(price: float, p30: float, p80: float) -> str:
    """Classify a single price against P30/P80 thresholds."""
    if price <= p30 or price <= ABSOLUTE_CHEAP_LIMIT:
        return PRICE_CHEAP
    if price <= p80:
        return PRICE_NORMAL
    return PRICE_EXPENSIVE


def classify_price_list(prices: List[float], p30: float, p80: float) -> List[str]:
    """Classify a list of prices."""
    return [classify_price(p, p30, p80) for p in prices]


def compute_price_thresholds(
    history_prices: List[float],
    fallback_prices: List[float],
) -> tuple[float, float]:
    """
    Compute P30 and P80 thresholds.
    Uses history_prices if enough samples exist, otherwise falls back to today's prices.
    """
    prices = (
        history_prices
        if len(history_prices) >= MIN_SAMPLES_FOR_CLASSIFICATION
        else fallback_prices
    )
    if not prices:
        return 0.0, 0.0
    p30 = _percentile(prices, PRICE_PERCENTILE_CHEAP)
    p80 = _percentile(prices, PRICE_PERCENTILE_EXPENSIVE)
    return p30, p80


async def async_get_price_thresholds(
    hass: HomeAssistant,
    price_entity_id: str,
    current_prices: List[float],
    trailing_hours: int = DEFAULT_TRAILING_HOURS,
) -> tuple[float, float]:
    """Fetch historical prices and compute P30/P80 thresholds."""
    end_time = dt_now()
    start_time = end_time - timedelta(hours=trailing_hours)

    try:
        recorder = get_instance(hass)

        def _get_history():
            return get_significant_states(hass, start_time, end_time, [price_entity_id])

        history = await recorder.async_add_executor_job(_get_history)
        states = history.get(price_entity_id, [])

        history_prices = []
        for s in states:
            try:
                if s.state not in ("unknown", "unavailable"):
                    history_prices.append(float(s.state))
            except (ValueError, TypeError):
                continue

    except Exception as err:
        _LOGGER.warning(
            "Could not fetch price history for %s, using today's prices: %s",
            price_entity_id,
            err,
        )
        history_prices = []

    p30, p80 = compute_price_thresholds(history_prices, current_prices)
    _LOGGER.debug(
        "Price thresholds: P30=%.3f P80=%.3f (from %d history + %d today)",
        p30,
        p80,
        len(history_prices),
        len(current_prices),
    )
    return p30, p80


def price_category_index(category: str) -> int:
    """Return numeric index for a price category (higher = more expensive)."""
    return {PRICE_CHEAP: 0, PRICE_NORMAL: 1, PRICE_EXPENSIVE: 2}.get(category, 1)


def filter_short_peaks(
    categories: List[str],
    interval_minutes: int,
    min_duration_minutes: int = 30,
) -> List[str]:
    """Replace expensive spikes shorter than min_duration with surrounding category."""
    import math

    if not categories or interval_minutes <= 0:
        return list(categories)

    min_slots = max(1, math.ceil(min_duration_minutes / interval_minutes))
    if min_slots <= 1:
        return list(categories)

    result = list(categories)
    index = 0
    total = len(categories)

    while index < total:
        if categories[index] != PRICE_EXPENSIVE:
            index += 1
            continue

        start = index
        while index < total and categories[index] == PRICE_EXPENSIVE:
            index += 1
        end = index - 1
        run_len = end - start + 1

        if run_len < min_slots:
            left = categories[start - 1] if start > 0 else PRICE_NORMAL
            right = categories[end + 1] if end + 1 < total else PRICE_NORMAL
            replacement = left if left != PRICE_EXPENSIVE else right
            for i in range(start, end + 1):
                result[i] = replacement

    return result
