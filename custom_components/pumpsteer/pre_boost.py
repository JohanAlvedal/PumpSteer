import logging
from typing import Optional, List, Tuple

from .settings import (
    PREBOOST_AGGRESSIVENESS_SCALING_FACTOR,
    MIN_PRICE_THRESHOLD_RATIO,
    MAX_PRICE_THRESHOLD_RATIO,
    BASE_PRICE_THRESHOLD_RATIO,
    MAX_PREBOOST_HOURS,
    PREBOOST_TEMP_THRESHOLD,
    PREBOOST_MIN_ADVANCE_FACTOR,
    PREBOOST_MAX_ADVANCE_FACTOR,
    PREBOOST_MIN_ADVANCE_HOURS,
    PREBOOST_MAX_ADVANCE_HOURS,
    SEVERITY_ADJUSTMENT_FACTOR,
    MIN_REASONABLE_TEMP,
    MAX_REASONABLE_TEMP,
    MIN_REASONABLE_PRICE,
    MAX_REASONABLE_PRICE,
    PREBOOST_REQUIRE_VERY_CHEAP_NOW,
    PREBOOST_MIN_DURATION_HOURS,
    PREBOOST_CHEAP_NOW_MULTIPLIER,
    # New constants for improved preboost logic
    TEMP_SEVERITY_DIVISOR,
    PRICE_SEVERITY_BASE,
    PRICE_SEVERITY_DIVISOR,
    DURATION_SEVERITY_DIVISOR,
    MAX_TEMP_SEVERITY,
    MAX_PRICE_SEVERITY,
    MAX_DURATION_SEVERITY,
    MAX_DURATION_LOOKAHEAD,
    MIN_ADVANCE_SAFETY_MARGIN,
    EXTREME_PRICE_ERROR_THRESHOLD,
    DEFAULT_PRICE_RATIO,  # <-- ADDED for consistency instead of hardcoded values
)

_LOGGER = logging.getLogger(__name__)


class PreboostValidationError(Exception):
    """Raised when preboost validation fails."""

    pass


def calculate_optimal_preboost_timing(
    inertia: float, peak_severity: float = 1.0
) -> Tuple[float, float]:
    """Calculate optimal preboost timing based on system inertia and peak severity."""
    inertia = max(0.5, min(5.0, inertia))
    peak_severity = max(0.5, min(3.0, peak_severity))

    base_min = inertia * PREBOOST_MIN_ADVANCE_FACTOR
    base_max = inertia * PREBOOST_MAX_ADVANCE_FACTOR
    severity_adjustment = (peak_severity - 1.0) * SEVERITY_ADJUSTMENT_FACTOR

    min_advance = max(PREBOOST_MIN_ADVANCE_HOURS, base_min + severity_adjustment)
    max_advance = min(PREBOOST_MAX_ADVANCE_HOURS, base_max + severity_adjustment)

    # Better handling of edge case
    if min_advance > max_advance:
        _LOGGER.warning(
            f"Calculated min_advance ({min_advance:.1f}h) > max_advance "
            f"({max_advance:.1f}h). Check configuration: inertia={inertia}, "
            f"severity={peak_severity}"
        )
        min_advance = max(0, max_advance - MIN_ADVANCE_SAFETY_MARGIN)

    _LOGGER.debug(
        f"Preboost timing: inertia={inertia:.1f}, severity={peak_severity:.1f} "
        f"→ {min_advance:.1f}-{max_advance:.1f}h advance"
    )

    return min_advance, max_advance


def calculate_peak_severity(
    temp_drop: float, price_ratio: float, duration_hours: int = 1
) -> float:
    """Calculate the severity of a cold/expensive peak using configurable constants."""
    temp_severity = min(MAX_TEMP_SEVERITY, abs(temp_drop) / TEMP_SEVERITY_DIVISOR)
    price_severity = min(
        MAX_PRICE_SEVERITY,
        max(0, (price_ratio - PRICE_SEVERITY_BASE) / PRICE_SEVERITY_DIVISOR),
    )
    duration_severity = min(
        MAX_DURATION_SEVERITY, duration_hours / DURATION_SEVERITY_DIVISOR
    )

    total_severity = 1.0 + (temp_severity + price_severity + duration_severity) / 3.0
    return max(0.5, min(3.0, total_severity))


def find_cold_expensive_peaks(
    temps: List[float],
    prices: List[float],
    cold_threshold: float,
    price_threshold: float,
    max_hours: int,
) -> List[Tuple[int, float, float, int]]:
    """Find peaks where temperature is cold and prices are expensive."""
    peaks = []

    if not temps or not prices:
        return peaks

    # IMPROVED: Use DEFAULT_PRICE_RATIO instead of hardcoded fallback
    max_price = max(prices[:max_hours]) if prices else DEFAULT_PRICE_RATIO
    if max_price <= 0:
        _LOGGER.warning(f"Invalid max_price <= 0, using fallback: {DEFAULT_PRICE_RATIO}")
        max_price = DEFAULT_PRICE_RATIO

    check_hours = min(max_hours, len(temps), len(prices))

    # Start from index 0 to include current hour
    for i in range(check_hours):
        temp = temps[i]
        price = prices[i]
        is_cold = temp < cold_threshold
        is_expensive = price >= price_threshold

        if is_cold and is_expensive:
            temp_drop = cold_threshold - temp
            price_ratio = price / max_price

            # Calculate duration more robustly
            duration = 1
            for j in range(i + 1, min(i + MAX_DURATION_LOOKAHEAD, check_hours)):
                if temps[j] < cold_threshold and prices[j] >= price_threshold:
                    duration += 1
                else:
                    break

            severity = calculate_peak_severity(temp_drop, price_ratio, duration)
            combined_score = temp_drop * price_ratio * duration
            peaks.append((i, severity, combined_score, duration))

            _LOGGER.debug(
                f"Peak found at hour {i}: temp={temp:.1f}°C (drop: {temp_drop:.1f}), "
                f"price={price:.3f} (ratio: {price_ratio:.2f}), "
                f"duration={duration}h, severity={severity:.2f}"
            )

    peaks.sort(key=lambda x: x[2], reverse=True)
    return peaks


def check_combined_preboost(
    temp_csv: str,
    prices: List[float],
    lookahead_hours: int = MAX_PREBOOST_HOURS,
    cold_threshold: float = PREBOOST_TEMP_THRESHOLD,
    price_threshold_ratio: float = 0.8,
    min_peak_hits: int = 1,
    aggressiveness: float = 0.0,
    inertia: float = 1.0,
) -> Optional[str]:
    """
    Simplified boost logic: Boost during the cheapest hours of the day.
    
    This replaces the complex cold+expensive peak prediction logic with a simpler
    approach: when enabled, boost during the N cheapest hours of the current day.
    The number of boost hours is determined by the aggressiveness setting.

    Args:
        temp_csv: CSV string of temperature forecasts (not used in simple mode)
        prices: List of price forecasts for the day (typically 24 hours)
        lookahead_hours: Hours to look ahead in forecast (typically 24)
        cold_threshold: Not used in simplified mode
        price_threshold_ratio: Not used in simplified mode
        min_peak_hits: Not used in simplified mode
        aggressiveness: Aggressiveness factor (0.0-5.0) - determines number of boost hours
        inertia: System thermal inertia factor (not used in simplified mode)

    Returns:
        "preboost" if current hour is among the cheapest hours, None otherwise

    Raises:
        PreboostValidationError: If validation fails critically
    """
    _LOGGER.debug(
        f"Boost check (SIMPLIFIED): aggressiveness={aggressiveness:.2f}"
    )

    try:
        # Validate price data
        if not prices or len(prices) < 1:
            _LOGGER.debug("No price data available for boost check")
            return None

        if not validate_price_data(prices, min(lookahead_hours, len(prices))):
            return None

        # Calculate number of boost hours based on aggressiveness (0-5)
        # aggressiveness 0 = 2 hours, aggressiveness 5 = 7 hours
        # This gives a range of 2-7 cheapest hours to boost
        boost_hours = int(2 + aggressiveness)
        boost_hours = max(1, min(boost_hours, 12))  # Limit between 1-12 hours
        
        _LOGGER.debug(f"Targeting {boost_hours} cheapest hours for boosting (aggressiveness={aggressiveness})")

        # Get current day's prices (up to 24 hours)
        day_prices = prices[:min(24, len(prices))]
        
        if len(day_prices) < boost_hours:
            _LOGGER.debug(f"Not enough price data ({len(day_prices)} hours) for boost calculation")
            return None

        # Find the cheapest hours
        # Create list of (hour_index, price) tuples and sort by price
        price_with_index = [(i, price) for i, price in enumerate(day_prices)]
        price_with_index.sort(key=lambda x: x[1])  # Sort by price
        
        # Get indices of the cheapest hours
        cheapest_hours = set(idx for idx, _ in price_with_index[:boost_hours])
        
        # Current hour is index 0
        current_hour_index = 0
        
        if current_hour_index in cheapest_hours:
            current_price = prices[current_hour_index]
            cheapest_price = price_with_index[0][1]
            _LOGGER.info(
                f"BOOST ACTIVATED: Current hour is among {boost_hours} cheapest hours. "
                f"Current price: {current_price:.3f}, cheapest: {cheapest_price:.3f}"
            )
            return "preboost"
        else:
            current_price = prices[current_hour_index]
            rank = next(i for i, (idx, _) in enumerate(price_with_index) if idx == current_hour_index) + 1
            _LOGGER.debug(
                f"Boost not activated: Current hour ranked #{rank} out of {len(day_prices)} hours "
                f"(price: {current_price:.3f}), need to be in top {boost_hours}"
            )
            return None

    except Exception as e:
        _LOGGER.error(f"Unexpected error in boost check: {e}")
        raise PreboostValidationError(f"Boost validation failed: {e}") from e


# Utility functions
def parse_temperature_csv_safe(temp_csv: str) -> Optional[List[float]]:
    """Safely parse CSV temperature data."""
    if not temp_csv or not isinstance(temp_csv, str):
        _LOGGER.warning(
            "Pre-boost: Received empty or invalid temperature forecast CSV"
        )
        return None

    try:
        temp_strings = [t.strip() for t in temp_csv.split(",") if t.strip()]
        if not temp_strings:
            return None

        temps = []
        for temp_str in temp_strings:
            try:
                temps.append(float(temp_str))
            except (ValueError, TypeError):
                _LOGGER.debug(f"Skipping invalid temperature value: {temp_str}")
                continue

        return temps if temps else None
    except Exception as e:
        _LOGGER.error(f"Error parsing temperature CSV: {e}")
        return None


def validate_temperature_data(temps: List[float], max_hours: int) -> bool:
    """Validate temperature data for reasonableness."""
    if not temps:
        return False

    check_hours = min(max_hours, len(temps))
    extreme_count = 0

    for i in range(check_hours):
        if temps[i] < MIN_REASONABLE_TEMP or temps[i] > MAX_REASONABLE_TEMP:
            extreme_count += 1
            _LOGGER.warning(f"Extreme temperature at hour {i}: {temps[i]}°C")

            # Fail if too many extreme values
            if extreme_count >= EXTREME_PRICE_ERROR_THRESHOLD:
                _LOGGER.error(
                    f"Too many extreme temperatures ({extreme_count}), "
                    f"failing validation"
                )
                return False

    return True


def validate_price_data(prices: List[float], max_hours: int) -> bool:
    """Validate price data for reasonableness."""
    if not prices:
        return False

    check_hours = min(max_hours, len(prices))
    extreme_count = 0

    for i in range(check_hours):
        if prices[i] < MIN_REASONABLE_PRICE or prices[i] > MAX_REASONABLE_PRICE:
            extreme_count += 1
            _LOGGER.warning(f"Extreme price at hour {i}: {prices[i]}")

            # Only fail validation if there are too many extreme values
            if extreme_count >= EXTREME_PRICE_ERROR_THRESHOLD:
                _LOGGER.error(
                    f"Too many extreme prices ({extreme_count}), "
                    f"failing validation"
                )
                return False

    return True


def check_future_warming_trend(temps: List[float], lookahead_hours: int) -> bool:
    """Check if there's a warming trend in the forecast."""
    if len(temps) < 2:
        return False

    current_temp = temps[0]
    check_hours = min(lookahead_hours, len(temps) - 1)
    future_temps = temps[1:check_hours + 1]

    # More nuanced warming trend detection
    if not future_temps:
        return False

    warming_hours = sum(1 for temp in future_temps if temp >= current_temp)
    warming_ratio = warming_hours / len(future_temps)

    # Consider it a warming trend if 80% or more of future hours are warmer
    is_warming = warming_ratio >= 0.8

    if is_warming:
        _LOGGER.debug(
            f"Warming trend detected: {warming_ratio:.1%} of future hours are warmer"
        )

    return is_warming


def calculate_adjusted_thresholds(
    aggressiveness: float, max_price: float
) -> Tuple[float, float]:
    """Calculate adjusted price thresholds based on aggressiveness factor (0-5)."""
    aggressiveness = max(0.0, min(5.0, aggressiveness))

    if max_price <= 0:
        raise ValueError(f"Invalid max_price: {max_price}")

    adjusted_ratio = max(
        MIN_PRICE_THRESHOLD_RATIO,
        min(
            MAX_PRICE_THRESHOLD_RATIO,
            BASE_PRICE_THRESHOLD_RATIO - (
                aggressiveness * PREBOOST_AGGRESSIVENESS_SCALING_FACTOR
            ),
        ),
    )

    price_threshold = max_price * adjusted_ratio
    return adjusted_ratio, price_threshold
