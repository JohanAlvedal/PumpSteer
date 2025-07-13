import numpy as np
from typing import List, Dict, Optional
import logging

_LOGGER = logging.getLogger(__name__)

# Constants for better maintainability
DEFAULT_PERCENTILES = [20, 40, 60, 80]
DEFAULT_EXTREME_MULTIPLIER = 1.5
MIN_SAMPLES_FOR_CLASSIFICATION = 5

# Categories in order from cheapest to most expensive
PRICE_CATEGORIES = [
    "extremely_cheap",
    "cheap",
    "normal",
    "expensive",
    "extremely_expensive"
]

ABSOLUTE_THRESHOLDS = [0.10, 0.30, 0.60, 1.00]
HYBRID_CATEGORIES = ["VERY_CHEAP", "CHEAP", "NORMAL", "EXPENSIVE", "VERY_EXPENSIVE"]

def validate_price_list(price_list: List[float], min_samples: int = MIN_SAMPLES_FOR_CLASSIFICATION) -> bool:
    """
    Validates if the price list is suitable for analysis.

    Args:
        price_list: List of electricity prices.
        min_samples: Minimum number of samples required.

    Returns:
        True if the list is valid, False otherwise.
    """
    if not price_list or len(price_list) < min_samples:
        return False
    # Warn about negative prices
    negative_prices = [p for p in price_list if p < 0]
    if negative_prices:
        _LOGGER.warning(f"Found {len(negative_prices)} negative prices in dataset")
    # Warn about extremely high values
    extreme_prices = [p for p in price_list if p > 10.0]  # > 10 SEK/kWh is considered extreme
    if extreme_prices:
        _LOGGER.warning(f"Found {len(extreme_prices)} extremely high prices (>10 kr/kWh)")
    return True

def classify_prices(
    price_list: List[float],
    percentiles: List[float] = None
) -> List[str]:
    """
    Takes a list of hourly electricity prices and returns a list of categories.

    Args:
        price_list: List of electricity prices.
        percentiles: Percentiles to use for classification (default: [20, 40, 60, 80]).

    Returns:
        List of categories: 'extremely_cheap', 'cheap', 'normal', 'expensive', 'extremely_expensive'.
    """
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
            categories.append(PRICE_CATEGORIES[0])  # extremely_cheap
        elif price < thresholds[1]:
            categories.append(PRICE_CATEGORIES[1])  # cheap
        elif price < thresholds[2]:
            categories.append(PRICE_CATEGORIES[2])  # normal
        elif price < thresholds[3]:
            categories.append(PRICE_CATEGORIES[3])  # expensive
        else:
            categories.append(PRICE_CATEGORIES[4])  # extremely_expensive

    return categories

def hybrid_classify_prices(price_list: List[float], percentiles: List[float] = DEFAULT_PERCENTILES) -> List[str]:
    """
    Applies a hybrid classification method combining absolute and relative thresholds.

    Args:
        price_list: List of electricity prices.
        percentiles: Percentiles for relative classification.

    Returns:
        List of hybrid price categories.
    """
    if not price_list or len(price_list) < MIN_SAMPLES_FOR_CLASSIFICATION:
        return ["unknown"] * len(price_list) if price_list else []

    thresholds = np.percentile(price_list, percentiles)
    result = []
    for price in price_list:
        # Absolute classification
        if price <= ABSOLUTE_THRESHOLDS[0]:
            absolute = "VERY_CHEAP"
        elif price <= ABSOLUTE_THRESHOLDS[1]:
            absolute = "CHEAP"
        elif price <= ABSOLUTE_THRESHOLDS[2]:
            absolute = "NORMAL"
        elif price <= ABSOLUTE_THRESHOLDS[3]:
            absolute = "EXPENSIVE"
        else:
            absolute = "VERY_EXPENSIVE"

        # Relative classification
        if price < thresholds[0]:
            relative = "VERY_CHEAP"
        elif price < thresholds[1]:
            relative = "CHEAP"
        elif price < thresholds[2]:
            relative = "NORMAL"
        elif price < thresholds[3]:
            relative = "EXPENSIVE"
        else:
            relative = "VERY_EXPENSIVE"

        # Hybrid logic: If either classification identifies it as very cheap/cheap/very expensive/expensive,
        # use that. Otherwise, default to normal.
        if "VERY_CHEAP" in (absolute, relative):
            result.append("VERY_CHEAP")
        elif "CHEAP" in (absolute, relative):
            result.append("CHEAP")
        elif "VERY_EXPENSIVE" in (absolute, relative):
            result.append("VERY_EXPENSIVE")
        elif "EXPENSIVE" in (absolute, relative):
            result.append("EXPENSIVE")
        else:
            result.append("NORMAL")
    return result

def get_daily_average(price_list: List[float]) -> float:
    """
    Returns the average of the daily electricity prices.

    Args:
        price_list: List of electricity prices.

    Returns:
        Average price, or 0.0 if the list is empty.
    """
    if not price_list:
        return 0.0
    return round(sum(price_list) / len(price_list), 3)

def get_price_statistics(price_list: List[float]) -> Dict[str, float]:
    """
    Returns basic statistics for the price list.

    Args:
        price_list: List of electricity prices.

    Returns:
        Dictionary with statistics (average, median, min, max, std).
    """
    if not price_list:
        return {"average": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}

    return {
        "average": round(np.mean(price_list), 3),
        "median": round(np.median(price_list), 3),
        "min": round(min(price_list), 3),
        "max": round(max(price_list), 3),
        "std": round(np.std(price_list), 3)
    }

def is_extreme(
    price: float,
    price_list: List[float],
    multiplier: float = DEFAULT_EXTREME_MULTIPLIER
) -> bool:
    """
    Returns True if the price is extremely high compared to the daily average.

    Args:
        price: The price to check.
        price_list: List of reference prices.
        multiplier: Multiplier for what is considered extreme (default: 1.5).

    Returns:
        True if the price is extremely high.
    """
    avg = get_daily_average(price_list)
    if avg == 0.0:
        return False
    return price > avg * multiplier

def count_categories(price_list: List[float]) -> Dict[str, int]:
    """
    Returns the number of hours for each category.
    More efficient than calling count_category() multiple times.

    Args:
        price_list: List of electricity prices.

    Returns:
        Dictionary with counts for each category.
    """
    categories = classify_prices(price_list)
    counts = {category: 0 for category in PRICE_CATEGORIES}
    counts["unknown"] = 0 # Added an "unknown" category count
    for category in categories:
        counts[category] += 1

    return counts

def count_category(price_list: List[float], target_category: str) -> int:
    """
    Returns the number of hours belonging to a specific category.

    Args:
        price_list: List of electricity prices.
        target_category: Category to count.

    Returns:
        Number of hours in the category.
    """
    if target_category not in PRICE_CATEGORIES and target_category != "unknown":
        raise ValueError(f"Unknown category: {target_category}. Valid categories: {PRICE_CATEGORIES + ['unknown']}")

    categories = classify_prices(price_list)
    return categories.count(target_category)

def find_cheapest_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Finds the cheapest hours in the price list.

    Args:
        price_list: List of electricity prices.
        num_hours: Number of hours to find.

    Returns:
        List of indices for the cheapest hours.
    """
    if not price_list or num_hours <= 0:
        return []

    # Create a list of (index, price) tuples and sort by price
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    indexed_prices.sort(key=lambda x: x[1])

    # Return the first num_hours indices
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]

def find_most_expensive_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Finds the most expensive hours in the price list.

    Args:
        price_list: List of electricity prices.
        num_hours: Number of hours to find.

    Returns:
        List of indices for the most expensive hours.
    """
    if not price_list or num_hours <= 0:
        return []

    # Create a list of (index, price) tuples and sort by price (descending)
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    indexed_prices.sort(key=lambda x: x[1], reverse=True)

    # Return the first num_hours indices
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]
