import logging
from typing import List

from .settings import (
    ABSOLUTE_CHEAP_LIMIT,
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
    from .settings import MIN_SAMPLES_FOR_CLASSIFICATION

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
    current_prices: List[float],
) -> tuple[float, float]:
    """Compute P30/P80 thresholds from today's prices only.

    Thresholds are relative to the current day's price spread, consistent with
    how Ngenic/Tibber classify prices. Caching per calendar day in sensor.py
    ensures they remain stable within the day and refresh at midnight.
    """
    if not current_prices:
        return 0.0, 0.0
    p30 = _percentile(current_prices, PRICE_PERCENTILE_CHEAP)
    p80 = _percentile(current_prices, PRICE_PERCENTILE_EXPENSIVE)
    _LOGGER.debug(
        "Price thresholds: P30=%.3f P80=%.3f (from %d today prices)",
        p30,
        p80,
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
