import logging
from typing import Optional

from .settings import COLD_HOUR_TEMP_THRESHOLD
from .settings import (
    AGGRESSIVENESS_SCALING_FACTOR,
    INERTIA_LEAD_TIME_FACTOR,
    MIN_PRICE_THRESHOLD_RATIO,
    MAX_PRICE_THRESHOLD_RATIO,
    BASE_PRICE_THRESHOLD_RATIO,
    MIN_LEAD_TIME,
    MAX_LEAD_TIME,
)

_LOGGER = logging.getLogger(__name__)

def check_combined_preboost(
    temp_csv: str,
    prices: list[float],
    lookahead_hours: int = 6,
    cold_threshold: float = COLD_HOUR_TEMP_THRESHOLD,
    price_threshold_ratio: float = 0.8,
    min_peak_hits: int = 1,
    aggressiveness: float = 0.0,
    inertia: float = 1.0
) -> Optional[str]:
    """
    Returns 'preboost' if a pre-heat should be activated for an expected cold and expensive period.
    This is a forward-looking function.
    
    Args:
        temp_csv: Comma-separated temperature values
        prices: List of electricity prices
        lookahead_hours: How many hours ahead to look
        cold_threshold: Temperature threshold for "cold" conditions
        price_threshold_ratio: Base ratio for price threshold calculation
        min_peak_hits: Minimum number of peak hits (currently unused)
        aggressiveness: Higher values make preboost harder to trigger (0.0-1.0)
        inertia: System inertia affecting lead time (higher = more lead time needed)
    
    Returns:
        'preboost' if conditions are met, None otherwise
    """
    try:
        temps = [float(t.strip()) for t in temp_csv.split(",") if t.strip() != ""]
        if not temps or not prices or len(temps) < lookahead_hours or len(prices) < lookahead_hours:
            _LOGGER.debug(
                "Pre-boost check: Not enough data (temps: %d, prices: %d, required: %d)",
                len(temps), len(prices), lookahead_hours
            )
            return None
    except Exception:
        _LOGGER.error("Pre-boost check: Error processing temperature data", exc_info=True)
        return None

    # Undvik preboost om det inte blir kallare än nu
    if all(temps[i] >= temps[0] for i in range(1, lookahead_hours)):
        _LOGGER.debug(
            "Pre-boost avbryts – framtida temperaturer är lika eller varmare än nu (nu: %.1f°C, framtid: %s)",
            temps[0],
            ", ".join([f"{t:.1f}" for t in temps[1:lookahead_hours]])
        )
        return None


    # Input validation
    if any(p < 0 for p in prices[:lookahead_hours]):
        _LOGGER.warning("Pre-boost check: Negative prices detected in forecast")
    
    if any(t < -50 or t > 50 for t in temps[:lookahead_hours]):
        _LOGGER.warning("Pre-boost check: Extreme temperatures detected in forecast")

    # Use aggressiveness to adjust the price threshold for enabling preboost
    # Higher aggressiveness makes it harder to preboost based on price (raises the threshold)
    # Formula: starts at 0.9, decreases by 0.04 per aggressiveness unit, clamped between 0.5-0.9
    adjusted_price_threshold_ratio = max(
        MIN_PRICE_THRESHOLD_RATIO, 
        min(MAX_PRICE_THRESHOLD_RATIO, 
            BASE_PRICE_THRESHOLD_RATIO - (aggressiveness * AGGRESSIVENESS_SCALING_FACTOR))
    )
    
    max_price = max(prices[:lookahead_hours])
    price_threshold = max_price * adjusted_price_threshold_ratio

    # Calculate lead time based on system inertia
    # Higher inertia means the system needs more time to react, so we start earlier
    # Formula: inertia * 0.75, clamped between 0.5-3.0 hours
    lead_time = min(MAX_LEAD_TIME, max(MIN_LEAD_TIME, inertia * INERTIA_LEAD_TIME_FACTOR))
    lead_hours = int(round(lead_time))

    _LOGGER.debug(
        "Pre-boost parameters: aggressiveness=%.2f, adjusted_threshold_ratio=%.2f, "
        "price_threshold=%.2f, inertia=%.2f, lead_hours=%d",
        aggressiveness, adjusted_price_threshold_ratio, price_threshold, inertia, lead_hours
    )

    # Main logic for pre-boost: Look for a future hour that is both cold and expensive
    for i in range(1, min(lookahead_hours, len(temps), len(prices))):    
        # Check if future hours are both cold and expensive
        if temps[i] < cold_threshold and prices[i] >= price_threshold:
            _LOGGER.debug(
                "Pre-boost check: Found cold+expensive period at hour %d (temp=%.1f°C, price=%.2f)",
                i, temps[i], prices[i]
            )
            
            if i <= lead_hours:
                _LOGGER.info(
                    "PREBOOST: Preboost activated (inertia: %.2f, lead_hours: %d, peak in %dh, "
                    "temp: %.1f°C, price: %.2f)",
                    inertia, lead_hours, i, temps[i], prices[i]
                )
                return "preboost"
            else:
                _LOGGER.debug(
                    "PREBOOST: Too early to preboost (peak in %dh, lead_hours: %d)",
                    i, lead_hours
                )
                return None

    _LOGGER.debug("Pre-boost check: No cold+expensive hours found in the forecast.")
    return None
