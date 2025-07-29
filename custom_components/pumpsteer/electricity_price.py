import numpy as np
from typing import List, Dict, Optional
import logging
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util.dt import now as dt_now
from datetime import timedelta
from homeassistant.core import HomeAssistant

# --- Legacy/Configuration Section (Settings imported from another file) ---
# These settings are typically defined elsewhere and represent configurable
# parameters for price classification. Depending on the project's evolution,
# these might be considered part of the 'legacy' configuration if not actively
# maintained or if they represent initial fixed values.
from .settings import (
    DEFAULT_PERCENTILES,
    DEFAULT_EXTREME_MULTIPLIER,
    MIN_SAMPLES_FOR_CLASSIFICATION,
    ABSOLUTE_CHEAP_LIMIT,
    PRICE_CATEGORIES,
    DEFAULT_TRAILING_HOURS,
    MAX_PRICE_WARNING_THRESHOLD,
    VERY_CHEAP_MULTIPLIER,
    CHEAP_MULTIPLIER,
    NORMAL_MULTIPLIER,
    EXPENSIVE_MULTIPLIER,
)

_LOGGER = logging.getLogger(__name__)


def validate_price_list(price_list: List[float], min_samples: int = MIN_SAMPLES_FOR_CLASSIFICATION) -> bool:
    """
    Validate that a price list is suitable for classification.
    This function ensures the input price list is not empty, contains enough
    samples, and only has numeric values. It also logs warnings for
    unexpected data, like negative or extremely high prices.

    Args:
        price_list: List of prices to validate.
        min_samples: Minimum number of samples required for a valid list.

    Returns:
        True if the price list is valid for processing, False otherwise.
    """
    if not price_list or len(price_list) < min_samples:
        return False

    # Check for None values in the list
    if any(p is None for p in price_list):
        _LOGGER.warning("Found None values in price list")
        return False

    # Ensure all values can be converted to floats (are numeric)
    try:
        float_prices = [float(p) for p in price_list]
    except (ValueError, TypeError) as e:
        _LOGGER.error(f"Non-numeric values found in price list: {e}")
        return False

    # Log warnings for unusual (but not necessarily invalid) price values
    negative_prices = [p for p in float_prices if p < 0]
    if negative_prices:
        _LOGGER.warning(f"Found {len(negative_prices)} negative prices in dataset")

    extreme_prices = [p for p in float_prices if p > MAX_PRICE_WARNING_THRESHOLD]
    if extreme_prices:
        _LOGGER.warning(f"Found {len(extreme_prices)} extremely high prices (>{MAX_PRICE_WARNING_THRESHOLD} kr/kWh)")

    return True


def classify_prices(price_list: List[float], percentiles: List[float] = None) -> List[str]:
    """
    Classify prices into categories (e.g., "very_cheap", "cheap", "normal", "expensive", "very_expensive")
    based on percentile thresholds calculated from the price list itself.
    This is a purely statistical classification based on the distribution of the current prices.

    Args:
        price_list: List of prices to classify.
        percentiles: Optional list of 4 percentile values (e.g., [10, 30, 70, 90])
                     that define the boundaries for the 5 categories. If None,
                     DEFAULT_PERCENTILES from settings will be used.

    Returns:
        List of strings, where each string is the category for the corresponding price.

    Raises:
        ValueError: If the number of provided percentiles is not exactly 4.
    """
    if percentiles is None:
        percentiles = DEFAULT_PERCENTILES

    # Validate the input price list before attempting classification
    if not validate_price_list(price_list):
        _LOGGER.debug(f"Invalid price list for classification (length: {len(price_list) if price_list else 0})")
        # Return "unknown" categories if the list is invalid
        return ["unknown"] * len(price_list) if price_list else []

    if len(percentiles) != 4:
        raise ValueError("Exactly 4 percentiles required for 5-category classification")

    # Calculate the actual price thresholds corresponding to the given percentiles
    thresholds = np.percentile(price_list, percentiles)

    # Use NumPy for efficient classification based on thresholds
    price_array = np.array(price_list)
    categories = np.select(
        [
            price_array < thresholds[0],  # Prices below the first percentile threshold
            price_array < thresholds[1],  # Prices between the first and second
            price_array < thresholds[2],  # Prices between the second and third
            price_array < thresholds[3]   # Prices between the third and fourth
        ],
        ["very_cheap", "cheap", "normal", "expensive"], # Categories for the above conditions
        default="very_expensive" # Default category for prices above the last threshold
    )

    return categories.tolist()


# --- Hybrid Section ---
# This function combines current price data with historical data from Home Assistant's
# recorder component to provide a more robust and context-aware classification.
# It's 'hybrid' because it leverages both real-time input and stored historical averages.
async def async_hybrid_classify_with_history(
    hass: HomeAssistant,
    price_list: List[float],
    price_entity_id: str,
    trailing_hours: int = DEFAULT_TRAILING_HOURS
) -> List[str]:
    """
    Classify prices using a hybrid approach that incorporates historical data from Home Assistant.
    It fetches historical prices for a given `trailing_hours` period, calculates an average
    from them, and then classifies current `price_list` entries relative to this historical average.
    This provides a more dynamic classification than just percentile-based.

    Args:
        hass: The Home Assistant instance, required to access its history data.
        price_list: The current list of prices to be classified.
        price_entity_id: The entity ID (e.g., "sensor.nordpool_spot_price")
                         from which historical price data will be fetched.
        trailing_hours: The number of hours of historical data to retrieve for the average calculation.

    Returns:
        List of price categories (strings) for each price in the input `price_list`.
    """
    if not price_list or len(price_list) < MIN_SAMPLES_FOR_CLASSIFICATION:
        # If the current price list is invalid, return "unknown" categories
        return ["unknown"] * len(price_list)

    end_time = dt_now() # Current time
    start_time = end_time - timedelta(hours=trailing_hours) # Start time for historical data fetch

    try:
        # Asynchronously get significant state changes for the price entity from Home Assistant's recorder.
        # This is wrapped in async_add_executor_job to prevent blocking the Home Assistant event loop.
        history = await hass.async_add_executor_job(
            get_significant_states,
            hass,
            start_time,
            end_time,
            [price_entity_id]
        )

        states = history.get(price_entity_id, []) # Extract states for the specific entity
        trailing_prices = []

        # Process historical states to extract valid numeric prices
        for s in states:
            try:
                if s.state not in ("unknown", "unavailable"):
                    trailing_prices.append(float(s.state))
            except (ValueError, TypeError):
                _LOGGER.debug(f"Skipping invalid state value from history: {s.state}")
                continue

        # Calculate the average price from the retrieved historical data
        if not trailing_prices:
            _LOGGER.warning("Could not retrieve trailing prices; fallback to daily average of current list.")
            avg_price = get_daily_average(price_list) # Fallback to current list average if history fails
        else:
            avg_price = get_daily_average(trailing_prices) # Use historical average

        _LOGGER.debug(f"Retrieved {len(trailing_prices)} trailing prices from history")
        _LOGGER.debug(f"Trailing average: {avg_price}")

    except Exception as e:
        _LOGGER.error(f"Error retrieving price history: {e}")
        avg_price = get_daily_average(price_list) # Fallback to current list average on error

    # Fallback to standard percentile classification if the calculated average is invalid (e.g., zero)
    if avg_price <= 0:
        _LOGGER.warning("Invalid average price calculated from history; using standard percentile classification.")
        return classify_prices(price_list)

    # Classify current prices based on the calculated historical average and predefined multipliers
    result = []
    for price in price_list:
        if price <= avg_price * VERY_CHEAP_MULTIPLIER:
            result.append("very_cheap")
        elif price <= avg_price * CHEAP_MULTIPLIER:
            result.append("cheap")
        elif price < avg_price * NORMAL_MULTIPLIER:
            # This is a specific 'hybrid' rule: if the price is below NORMAL_MULTIPLIER
            # but also below an ABSOLUTE_CHEAP_LIMIT, it's still classified as "cheap".
            # This blends relative (to average) and absolute thresholds.
            result.append("cheap" if price < ABSOLUTE_CHEAP_LIMIT else "normal")
        elif price < avg_price * EXPENSIVE_MULTIPLIER:
            result.append("expensive")
        else:
            result.append("very_expensive")

    return result


def get_daily_average(price_list: List[float]) -> float:
    """
    Calculate the average of a list of prices.

    Args:
        price_list: List of float prices.

    Returns:
        The average price, rounded to 3 decimal places. Returns 0.0 if the list is empty.
    """
    if not price_list:
        return 0.0
    return round(sum(price_list) / len(price_list), 3)


def get_price_statistics(price_list: List[float]) -> Dict[str, float]:
    """
    Calculate various descriptive statistics for a list of prices.
    Includes average, median, minimum, maximum, and standard deviation.

    Args:
        price_list: List of float prices.

    Returns:
        A dictionary containing the calculated statistics. Returns all zeros
        if the input list is empty.
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


def is_extreme(price: float, price_list: List[float], multiplier: float = DEFAULT_EXTREME_MULTIPLIER) -> bool:
    """
    Check if a single price is considered "extreme" relative to the average of a given price list.
    An extreme price is defined as exceeding the average by a certain multiplier.

    Args:
        price: The individual price to check.
        price_list: The reference list of prices used to calculate the average.
        multiplier: A factor by which the average price is multiplied to determine the extreme threshold.

    Returns:
        True if the price is extreme, False otherwise. Returns False if the average is zero.
    """
    avg = get_daily_average(price_list)
    if avg == 0.0:
        return False
    return price > avg * multiplier


def count_categories(price_list: List[float]) -> Dict[str, int]:
    """
    Count the occurrences of each price category (e.g., "very_cheap", "expensive")
    after classifying all prices in the input list using the `classify_prices` function.

    Args:
        price_list: List of prices to classify and count.

    Returns:
        A dictionary where keys are category names and values are their counts.
        Includes "unknown" category if any prices couldn't be classified.
    """
    categories = classify_prices(price_list)
    # Initialize counts for all possible categories, including 'unknown'
    counts = {category: 0 for category in PRICE_CATEGORIES}
    counts["unknown"] = 0

    for category in categories:
        counts[category] += 1

    return counts


def count_category(price_list: List[float], target_category: str) -> int:
    """
    Count the occurrences of a specific price category within a list of prices.

    Args:
        price_list: List of prices to classify.
        target_category: The specific category (e.g., "cheap", "expensive") to count.

    Returns:
        The number of prices classified into the `target_category`.

    Raises:
        ValueError: If `target_category` is not a recognized category.
    """
    valid_categories = PRICE_CATEGORIES + ["unknown"]
    if target_category not in valid_categories:
        raise ValueError(f"Unknown category: {target_category}. Valid categories: {valid_categories}")

    categories = classify_prices(price_list)
    return categories.count(target_category)


def find_cheapest_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Find the indices (positions) of the `num_hours` cheapest prices in the list.
    The indices correspond to the original position in the `price_list`.

    Args:
        price_list: List of prices.
        num_hours: The number of cheapest hours (indices) to retrieve. Must be greater than 0.

    Returns:
        A list of integer indices representing the positions of the cheapest hours.
        Returns an empty list if `price_list` is empty or `num_hours` is not positive.
    """
    if not price_list or num_hours <= 0:
        return []

    # Pair each price with its original index
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    # Sort by price in ascending order
    indexed_prices.sort(key=lambda x: x[1])
    # Return the indices of the cheapest hours
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]


def find_most_expensive_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Find the indices (positions) of the `num_hours` most expensive prices in the list.
    The indices correspond to the original position in the `price_list`.

    Args:
        price_list: List of prices.
        num_hours: The number of most expensive hours (indices) to retrieve. Must be greater than 0.

    Returns:
        A list of integer indices representing the positions of the most expensive hours.
        Returns an empty list if `price_list` is empty or `num_hours` is not positive.
    """
    if not price_list or num_hours <= 0:
        return []

    # Pair each price with its original index
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    # Sort by price in descending order
    indexed_prices.sort(key=lambda x: x[1], reverse=True)
    # Return the indices of the most expensive hours
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]
