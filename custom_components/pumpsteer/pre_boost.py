import logging
from typing import Optional, List, Tuple

from . import settings as _settings
from .electricity_price import find_cheapest_hours

_LOGGER = logging.getLogger(__name__)


def _get_setting(name: str, default):
    """Fetch a setting with graceful fallback for older installations."""
    if hasattr(_settings, name):
        return getattr(_settings, name)

    _LOGGER.warning(
        "Setting %s missing in settings.py, falling back to default %s", name, default
    )
    return default


PREBOOST_AGGRESSIVENESS_SCALING_FACTOR = _get_setting(
    "PREBOOST_AGGRESSIVENESS_SCALING_FACTOR", 0.04
)
MIN_PRICE_THRESHOLD_RATIO = _get_setting("MIN_PRICE_THRESHOLD_RATIO", 0.5)
MAX_PRICE_THRESHOLD_RATIO = _get_setting("MAX_PRICE_THRESHOLD_RATIO", 0.9)
BASE_PRICE_THRESHOLD_RATIO = _get_setting("BASE_PRICE_THRESHOLD_RATIO", 0.9)
MAX_PREBOOST_HOURS = _get_setting("MAX_PREBOOST_HOURS", 6)
PREBOOST_TEMP_THRESHOLD = _get_setting("PREBOOST_TEMP_THRESHOLD", 2.0)
PREBOOST_MIN_ADVANCE_FACTOR = _get_setting("PREBOOST_MIN_ADVANCE_FACTOR", 0.5)
PREBOOST_MAX_ADVANCE_FACTOR = _get_setting("PREBOOST_MAX_ADVANCE_FACTOR", 1.2)
PREBOOST_MIN_ADVANCE_HOURS = _get_setting("PREBOOST_MIN_ADVANCE_HOURS", 1.0)
PREBOOST_MAX_ADVANCE_HOURS = _get_setting("PREBOOST_MAX_ADVANCE_HOURS", 3.0)
SEVERITY_ADJUSTMENT_FACTOR = _get_setting("SEVERITY_ADJUSTMENT_FACTOR", 0.3)
MIN_REASONABLE_TEMP = _get_setting("MIN_REASONABLE_TEMP", -50.0)
MAX_REASONABLE_TEMP = _get_setting("MAX_REASONABLE_TEMP", 50.0)
MIN_REASONABLE_PRICE = _get_setting("MIN_REASONABLE_PRICE", -2.0)
MAX_REASONABLE_PRICE = _get_setting("MAX_REASONABLE_PRICE", 15.0)
PREBOOST_REQUIRE_VERY_CHEAP_NOW = _get_setting(
    "PREBOOST_REQUIRE_VERY_CHEAP_NOW", True
)
PREBOOST_MIN_DURATION_HOURS = _get_setting("PREBOOST_MIN_DURATION_HOURS", 2)
PREBOOST_CHEAP_NOW_MULTIPLIER = _get_setting("PREBOOST_CHEAP_NOW_MULTIPLIER", 0.6)
TEMP_SEVERITY_DIVISOR = _get_setting("TEMP_SEVERITY_DIVISOR", 3.0)
PRICE_SEVERITY_BASE = _get_setting("PRICE_SEVERITY_BASE", 0.7)
PRICE_SEVERITY_DIVISOR = _get_setting("PRICE_SEVERITY_DIVISOR", 0.2)
DURATION_SEVERITY_DIVISOR = _get_setting("DURATION_SEVERITY_DIVISOR", 3.0)
MAX_TEMP_SEVERITY = _get_setting("MAX_TEMP_SEVERITY", 2.0)
MAX_PRICE_SEVERITY = _get_setting("MAX_PRICE_SEVERITY", 2.0)
MAX_DURATION_SEVERITY = _get_setting("MAX_DURATION_SEVERITY", 1.5)
MAX_DURATION_LOOKAHEAD = _get_setting("MAX_DURATION_LOOKAHEAD", 4)
MIN_ADVANCE_SAFETY_MARGIN = _get_setting("MIN_ADVANCE_SAFETY_MARGIN", 0.5)
EXTREME_PRICE_ERROR_THRESHOLD = _get_setting("EXTREME_PRICE_ERROR_THRESHOLD", 5)
DEFAULT_PRICE_RATIO = _get_setting("DEFAULT_PRICE_RATIO", 0.5)


class PreboostValidationError(Exception):
    """Raised when preboost validation fails."""

    pass


def check_cheap_boost(
    prices: List[float],
    num_cheap_hours: int = 3,
    lookahead_hours: int = 24,
) -> Optional[str]:
    """
    Simplified cheap boost logic that activates during the cheapest hours.
    
    Args:
        prices: List of price forecasts (hourly)
        num_cheap_hours: Number of cheapest hours to boost (from input_number)
        lookahead_hours: How many hours ahead to consider
        
    Returns:
        "preboost" if current hour is in the cheapest N hours, None otherwise
    """
    if not prices or num_cheap_hours <= 0:
        _LOGGER.debug("Cheap boost: No prices or invalid num_cheap_hours")
        return None
        
    if len(prices) < 2:
        _LOGGER.debug("Cheap boost: Insufficient price data")
        return None
    
    # Only look at the lookahead window
    price_window = prices[:min(lookahead_hours, len(prices))]
    
    # Find the cheapest hours in the window
    cheap_hour_indices = find_cheapest_hours(price_window, num_cheap_hours)
    
    # Check if the current hour (index 0) is one of the cheapest
    is_cheap_hour = 0 in cheap_hour_indices
    
    if is_cheap_hour:
        _LOGGER.info(
            f"CHEAP BOOST ACTIVATED: Current hour is one of the {num_cheap_hours} "
            f"cheapest hours. Current price: {prices[0]:.3f}, "
            f"cheap hours: {sorted(cheap_hour_indices)}"
        )
        return "preboost"
    else:
        _LOGGER.debug(
            f"Cheap boost: Current hour not in cheapest {num_cheap_hours} hours. "
            f"Cheap hours: {sorted(cheap_hour_indices)}"
        )
        return None


