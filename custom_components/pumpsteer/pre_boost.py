import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)

def check_combined_preboost(
    temp_csv: str,
    prices: list[float],
    lookahead_hours: int = 6,
    cold_threshold: float = 2.0,
    price_threshold_ratio: float = 0.8,
    min_peak_hits: int = 1,
    aggressiveness: float = 0.0,
    inertia: float = 1.0
) -> Optional[str]:
    """
    Returns 'preboost' if a pre-heat should be activated for an expected cold and expensive period.
    This is a forward-looking function.
    """
    try:
        temps = [float(t.strip()) for t in temp_csv.split(",") if t.strip() != ""]
        if not temps or not prices or len(temps) < lookahead_hours or len(prices) < lookahead_hours:
            _LOGGER.debug(
                "Pre-boost check: Not enough data (temps: %d, prices: %d)",
                len(temps), len(prices)
            )
            return None
    except Exception:
        _LOGGER.error("Pre-boost check: Error processing data", exc_info=True)
        return None

    # Use aggressiveness to adjust the price threshold for enabling preboost
    # Higher aggressiveness makes it harder to preboost based on price (raises the threshold)
    adjusted_price_threshold_ratio = max(0.5, min(0.9, 0.9 - (aggressiveness * 0.04)))
    max_price = max(prices[:lookahead_hours])
    price_threshold = max_price * adjusted_price_threshold_ratio

    # Main logic for pre-boost: Look for a future hour that is both cold and expensive
    lead_time = min(3.0, max(0.5, inertia * 0.75))
    lead_hours = int(round(lead_time))

    for i in range(1, lookahead_hours):
        # Check if future hours are both cold and expensive
        if temps[i] < cold_threshold and prices[i] >= price_threshold:
            if i <= lead_hours:
                _LOGGER.debug(
                    f"PREBOOST: Preboost activated (inertia: {inertia:.2f}, lead_hours: {lead_hours}, peak in {i}h)"
                )
                return "preboost"
            else:
                _LOGGER.debug(
                    f"PREBOOST: Too early to preboost (peak in {i}h, lead_hours: {lead_hours})"
                )
                return None

    _LOGGER.debug("Preboost: No cold+expensive hours found in the forecast.")
    return None
