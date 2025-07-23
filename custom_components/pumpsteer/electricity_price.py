import numpy as np
from typing import List, Dict, Optional
import logging
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util.dt import now as dt_now
from datetime import timedelta
from homeassistant.core import HomeAssistant

from .settings import (
    DEFAULT_PERCENTILES,
    DEFAULT_EXTREME_MULTIPLIER,
    MIN_SAMPLES_FOR_CLASSIFICATION,
    ABSOLUTE_CHEAP_LIMIT,
    PRICE_CATEGORIES,
)

_LOGGER = logging.getLogger(__name__)

# Pris-kategorier i rätt ordning
# Använder PRICE_CATEGORIES från settings.py

# Används ej längre, men fanns tidigare i Tibber-liknande logik
# HYBRID_CATEGORIES = ["VERY_CHEAP", "CHEAP", "NORMAL", "EXPENSIVE", "VERY_EXPENSIVE"]

def validate_price_list(price_list: List[float], min_samples: int = MIN_SAMPLES_FOR_CLASSIFICATION) -> bool:
    if not price_list or len(price_list) < min_samples:
        return False
    negative_prices = [p for p in price_list if p < 0]
    if negative_prices:
        _LOGGER.warning(f"Found {len(negative_prices)} negative prices in dataset")
    extreme_prices = [p for p in price_list if p > 4.0]
    if extreme_prices:
        _LOGGER.warning(f"Found {len(extreme_prices)} extremely high prices (>4 kr/kWh)")
    return True

def classify_prices(price_list: List[float], percentiles: List[float] = None) -> List[str]:
    if percentiles is None:
        percentiles = DEFAULT_PERCENTILES

    if not validate_price_list(price_list):
        _LOGGER.debug(f"Invalid price list for classification (length: {len(price_list) if price_list else 0})")
        return ["unknown"] * len(price_list) if price_list else []

    if len(percentiles) != 4:
        raise ValueError("Exactly 4 percentiles required for 5-category classification")

    thresholds = np.percentile(price_list, percentiles)
    categories = []

    for price in price_list:
        if price < thresholds[0]:
            categories.append("very_cheap")
        elif price < thresholds[1]:
            categories.append("cheap")
        elif price < thresholds[2]:
            categories.append("normal")
        elif price < thresholds[3]:
            categories.append("expensive")
        else:
            categories.append("very_expensive")

    return categories

async def async_hybrid_classify_with_history(
    hass: HomeAssistant,
    price_list: List[float],
    price_entity_id: str,
    trailing_hours: int = 72
) -> List[str]:
    if not price_list or len(price_list) < MIN_SAMPLES_FOR_CLASSIFICATION:
        return ["unknown"] * len(price_list)

    end_time = dt_now()
    start_time = end_time - timedelta(hours=trailing_hours)

    history = await hass.async_add_executor_job(
        get_significant_states,
        hass,
        start_time,
        end_time,
        [price_entity_id]
    )

    states = history.get(price_entity_id, [])
    trailing_prices = [
        float(s.state)
        for s in states
        if s.state not in ("unknown", "unavailable")
    ]

    if not trailing_prices:
        _LOGGER.warning("Could not retrieve trailing prices; fallback to daily average.")
        avg_price = get_daily_average(price_list)
    else:
        avg_price = get_daily_average(trailing_prices)

    _LOGGER.debug(f"Retrieved {len(trailing_prices)} trailing prices from history")
    _LOGGER.debug(f"Trailing average: {avg_price}")

    result = []
    for price in price_list:
        if price <= avg_price * 0.60:
            result.append("very_cheap")
        elif price <= avg_price * 0.90:
            result.append("cheap")
        elif price < avg_price * 1.15:
            result.append("cheap" if price < ABSOLUTE_CHEAP_LIMIT else "normal")
        elif price < avg_price * 1.40:
            result.append("expensive")
        else:
            result.append("very_expensive")

    return result

def get_daily_average(price_list: List[float]) -> float:
    if not price_list:
        return 0.0
    return round(sum(price_list) / len(price_list), 3)

def get_price_statistics(price_list: List[float]) -> Dict[str, float]:
    if not price_list:
        return {"average": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}

    return {
        "average": round(np.mean(price_list), 3),
        "median": round(np.median(price_list), 3),
        "min": round(min(price_list), 3),
        "max": round(max(price_list), 3),
        "std": round(np.std(price_list), 3)
    }

def is_extreme(price: float, price_list: List[float], multiplier: float = DEFAULT_EXTREME_MULTIPLIER) -> bool:
    avg = get_daily_average(price_list)
    if avg == 0.0:
        return False
    return price > avg * multiplier

def count_categories(price_list: List[float]) -> Dict[str, int]:
    categories = classify_prices(price_list)
    counts = {category: 0 for category in PRICE_CATEGORIES}
    counts["unknown"] = 0
    for category in categories:
        counts[category] += 1
    return counts

def count_category(price_list: List[float], target_category: str) -> int:
    if target_category not in PRICE_CATEGORIES and target_category != "unknown":
        raise ValueError(f"Unknown category: {target_category}. Valid categories: {PRICE_CATEGORIES + ['unknown']}")

    categories = classify_prices(price_list)
    return categories.count(target_category)

def find_cheapest_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    if not price_list or num_hours <= 0:
        return []

    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    indexed_prices.sort(key=lambda x: x[1])
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]

def find_most_expensive_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    if not price_list or num_hours <= 0:
        return []

    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    indexed_prices.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]
