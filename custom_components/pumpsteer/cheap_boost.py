import logging
from typing import Optional, List

_LOGGER = logging.getLogger(__name__)


def check_cheap_boost(
    prices: List[float],
    boost_hours: int = 3,
    lookahead_hours: int = 24,
) -> Optional[str]:
    """
    Check if cheap boost should be activated based on current price being among the cheapest.
    
    Args:
        prices: List of price forecasts
        boost_hours: Number of cheapest hours to boost during
        lookahead_hours: Hours to look ahead in forecast
        
    Returns:
        "cheap_boost" if boost should be activated, None otherwise
    """
    if not prices or len(prices) == 0:
        _LOGGER.warning("No price data available for cheap boost check")
        return None
        
    if boost_hours <= 0:
        _LOGGER.debug("Cheap boost hours set to 0, skipping cheap boost")
        return None
    
    # Limit lookahead to available data
    check_hours = min(lookahead_hours, len(prices))
    if check_hours < 2:
        _LOGGER.warning("Insufficient price data for cheap boost analysis")
        return None
    
    # Get the prices we'll analyze
    price_window = prices[:check_hours]
    current_price = prices[0]
    
    # Sort prices to find the cheapest hours
    sorted_prices = sorted(enumerate(price_window), key=lambda x: x[1])
    
    # Get the indices of the N cheapest hours
    cheapest_indices = set(idx for idx, _ in sorted_prices[:boost_hours])
    
    # Check if current hour (index 0) is among the cheapest
    if 0 in cheapest_indices:
        cheapest_prices = [price for _, price in sorted_prices[:boost_hours]]
        avg_cheap = sum(cheapest_prices) / len(cheapest_prices)
        avg_all = sum(price_window) / len(price_window)
        
        _LOGGER.info(
            f"CHEAP BOOST ACTIVATED: Current price {current_price:.3f} is among "
            f"the {boost_hours} cheapest hours. "
            f"Avg cheap: {avg_cheap:.3f}, Avg all: {avg_all:.3f}"
        )
        return "cheap_boost"
    else:
        # Find where current price ranks
        rank = sum(1 for price in price_window if price < current_price) + 1
        _LOGGER.debug(
            f"Cheap boost not activated: Current price {current_price:.3f} "
            f"ranks #{rank} out of {check_hours} hours (need top {boost_hours})"
        )
        return None
