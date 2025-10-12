"""
Cheap Boost Module for PumpSteer
Simplified boost logic that activates during the cheapest hours
"""
import logging
from typing import List, Optional

_LOGGER = logging.getLogger(__name__)


def check_cheap_boost(
    prices: List[float],
    boost_hours: int,
    current_slot_index: int = 0,
) -> bool:
    """
    Check if cheap boost should be activated.
    
    Args:
        prices: List of electricity prices for the day
        boost_hours: Number of cheapest hours to boost during
        current_slot_index: Current hour index in the price list
        
    Returns:
        True if cheap boost should be activated, False otherwise
    """
    if not prices or boost_hours <= 0:
        _LOGGER.debug("Cheap boost: disabled or no price data available")
        return False
    
    if current_slot_index >= len(prices):
        _LOGGER.warning(
            f"Cheap boost: current_slot_index {current_slot_index} >= "
            f"prices length {len(prices)}"
        )
        return False
    
    # Find the indices of the cheapest hours
    try:
        # Create a list of (price, index) tuples
        price_with_indices = [(price, idx) for idx, price in enumerate(prices)]
        
        # Sort by price (lowest first)
        price_with_indices.sort(key=lambda x: x[0])
        
        # Get the indices of the N cheapest hours
        cheapest_indices = [idx for _, idx in price_with_indices[:boost_hours]]
        
        # Check if current hour is one of the cheapest
        is_cheap_hour = current_slot_index in cheapest_indices
        
        if is_cheap_hour:
            current_price = prices[current_slot_index]
            _LOGGER.info(
                f"CHEAP BOOST ACTIVATED: Current hour ({current_slot_index}) is among "
                f"the {boost_hours} cheapest hours. Price: {current_price:.3f}"
            )
        else:
            _LOGGER.debug(
                f"Cheap boost: Current hour ({current_slot_index}) is not among "
                f"the {boost_hours} cheapest hours"
            )
        
        return is_cheap_hour
        
    except Exception as e:
        _LOGGER.error(f"Error in cheap boost check: {e}")
        return False


def get_cheapest_hours_info(
    prices: List[float],
    boost_hours: int,
) -> Optional[dict]:
    """
    Get information about the cheapest hours.
    
    Args:
        prices: List of electricity prices
        boost_hours: Number of cheapest hours to find
        
    Returns:
        Dictionary with cheapest hours information or None
    """
    if not prices or boost_hours <= 0:
        return None
    
    try:
        # Create a list of (price, index) tuples
        price_with_indices = [(price, idx) for idx, price in enumerate(prices)]
        
        # Sort by price (lowest first)
        price_with_indices.sort(key=lambda x: x[0])
        
        # Get the N cheapest hours
        cheapest_hours = price_with_indices[:boost_hours]
        
        return {
            'cheapest_hours': [idx for _, idx in cheapest_hours],
            'cheapest_prices': [price for price, _ in cheapest_hours],
            'avg_cheap_price': sum(price for price, _ in cheapest_hours) / len(cheapest_hours),
        }
    except Exception as e:
        _LOGGER.error(f"Error getting cheapest hours info: {e}")
        return None
