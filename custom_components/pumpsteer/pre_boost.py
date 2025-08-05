# Fil: pre_boost.py
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
)

_LOGGER = logging.getLogger(__name__)


def calculate_optimal_preboost_timing(
    inertia: float,
    peak_severity: float = 1.0
) -> Tuple[float, float]:
    inertia = max(0.5, min(5.0, inertia))
    peak_severity = max(0.5, min(3.0, peak_severity))

    base_min = inertia * PREBOOST_MIN_ADVANCE_FACTOR
    base_max = inertia * PREBOOST_MAX_ADVANCE_FACTOR
    severity_adjustment = (peak_severity - 1.0) * SEVERITY_ADJUSTMENT_FACTOR

    min_advance = max(PREBOOST_MIN_ADVANCE_HOURS, base_min + severity_adjustment)
    max_advance = min(PREBOOST_MAX_ADVANCE_HOURS, base_max + severity_adjustment)

    if min_advance > max_advance:
        min_advance = max_advance - 0.5

    _LOGGER.debug(
        f"Preboost timing: inertia={inertia:.1f}, severity={peak_severity:.1f} "
        f"→ {min_advance:.1f}-{max_advance:.1f}h advance"
    )

    return min_advance, max_advance


def calculate_peak_severity(
    temp_drop: float,
    price_ratio: float,
    duration_hours: int = 1
) -> float:
    temp_severity = min(2.0, abs(temp_drop) / 3.0)
    price_severity = min(2.0, (price_ratio - 0.7) / 0.2)
    duration_severity = min(1.5, duration_hours / 3.0)
    total_severity = 1.0 + (temp_severity + price_severity + duration_severity) / 3.0
    return max(0.5, min(3.0, total_severity))


def find_cold_expensive_peaks(
    temps: List[float],
    prices: List[float],
    cold_threshold: float,
    price_threshold: float,
    max_hours: int
) -> List[Tuple[int, float, float, int]]:
    peaks = []
    max_price = max(prices[:max_hours]) if prices else 1.0
    check_hours = min(max_hours, len(temps), len(prices))

    for i in range(1, check_hours):
        temp = temps[i]
        price = prices[i]
        is_cold = temp < cold_threshold
        is_expensive = price >= price_threshold

        if is_cold and is_expensive:
            temp_drop = cold_threshold - temp
            price_ratio = price / max_price if max_price > 0 else 0.5
            duration = 1
            for j in range(i + 1, min(i + 4, check_hours)):
                if temps[j] < cold_threshold and prices[j] >= price_threshold:
                    duration += 1
                else:
                    break
            severity = calculate_peak_severity(temp_drop, price_ratio, duration)
            combined_score = temp_drop * price_ratio * duration
            peaks.append((i, severity, combined_score, duration))
            _LOGGER.debug(
                f"Peak found at hour {i}: temp={temp:.1f}°C (drop: {temp_drop:.1f}), "
                f"price={price:.3f} (ratio: {price_ratio:.2f}), duration={duration}h, "
                f"severity={severity:.2f}"
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
    inertia: float = 1.0
) -> Optional[str]:
    _LOGGER.debug(
        f"Pre-boost check (IMPROVED): lookahead={lookahead_hours}h, "
        f"cold_threshold={cold_threshold}°C, aggressiveness={aggressiveness:.2f}, "
        f"inertia={inertia:.2f}"
    )

    temps = parse_temperature_csv_safe(temp_csv)
    if temps is None:
        return None

    if len(temps) < lookahead_hours or (prices and len(prices) < lookahead_hours):
        original_lookahead = lookahead_hours
        lookahead_hours = min(len(temps), len(prices) if prices else len(temps))
        _LOGGER.debug(f"Adjusting lookahead: {original_lookahead}h → {lookahead_hours}h")
        if lookahead_hours < 2:
            _LOGGER.warning("Insufficient data for meaningful pre-boost analysis")
            return None

    if not validate_temperature_data(temps, lookahead_hours):
        return None
    if not validate_price_data(prices, lookahead_hours):
        return None
    if check_future_warming_trend(temps, lookahead_hours):
        _LOGGER.debug("Pre-boost: Skipping due to warming trend")
        return None

    max_price = max(prices[:lookahead_hours]) if prices else 0.0
    if max_price <= 0:
        _LOGGER.warning("Invalid max price for pre-boost analysis")
        return None

    adjusted_ratio, price_threshold = calculate_adjusted_thresholds(aggressiveness, max_price)
    peaks = find_cold_expensive_peaks(temps, prices, cold_threshold, price_threshold, lookahead_hours)

    if not peaks:
        _LOGGER.debug("No cold+expensive peaks found in forecast")
        return None

    for peak_hour, severity, combined_score, duration in peaks:
        hours_to_peak = peak_hour

        if duration < PREBOOST_MIN_DURATION_HOURS:
            _LOGGER.debug(f"Preboost skipped: Peak too short ({duration}h < {PREBOOST_MIN_DURATION_HOURS}h)")
            continue

        current_price = prices[0] if prices else 0.0
        cheap_now_threshold = max_price * PREBOOST_CHEAP_NOW_MULTIPLIER
        if PREBOOST_REQUIRE_VERY_CHEAP_NOW and current_price > cheap_now_threshold:
            _LOGGER.debug(
                f"Preboost skipped: current price {current_price:.3f} > "
                f"threshold {cheap_now_threshold:.3f} (not 'very cheap')"
            )
            continue

        min_advance, max_advance = calculate_optimal_preboost_timing(inertia, severity)

        _LOGGER.debug(
            f"Peak at hour {peak_hour}: severity={severity:.2f}, "
            f"optimal advance: {min_advance:.1f}-{max_advance:.1f}h, "
            f"actual: {hours_to_peak}h"
        )

        if min_advance <= hours_to_peak <= max_advance:
            _LOGGER.info(
                f"PREBOOST ACTIVATED (OPTIMAL TIMING): Peak in {hours_to_peak}h "
                f"(optimal: {min_advance:.1f}-{max_advance:.1f}h), "
                f"severity: {severity:.2f}, duration: {duration}h, "
                f"temp: {temps[peak_hour]:.1f}°C, price: {prices[peak_hour]:.3f}"
            )
            return "preboost"

        elif hours_to_peak > max_advance:
            _LOGGER.debug(
                f"Peak too far away: {hours_to_peak}h > {max_advance}h (will check again later)"
            )
            continue

        elif hours_to_peak < min_advance:
            _LOGGER.debug(
                f"Peak too close: {hours_to_peak}h < {min_advance}h (should have started earlier)"
            )
            continue

    _LOGGER.debug("No peaks within optimal timing windows")
    return None


# Behåll befintliga utility-funktioner
def parse_temperature_csv_safe(temp_csv: str) -> Optional[List[float]]:
    """Säkert parsa CSV-temperaturdata (befintlig implementation)"""
    if not temp_csv or not isinstance(temp_csv, str):
        _LOGGER.warning("Pre-boost: Received empty or invalid temperature forecast CSV")
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
                continue
        
        return temps if temps else None
    except Exception as e:
        _LOGGER.error(f"Error parsing temperature CSV: {e}")
        return None


def validate_temperature_data(temps: List[float], max_hours: int) -> bool:
    """Validera temperaturdata (befintlig implementation)"""
    if not temps:
        return False
    
    check_hours = min(max_hours, len(temps))
    for i in range(check_hours):
        if temps[i] < MIN_REASONABLE_TEMP or temps[i] > MAX_REASONABLE_TEMP:
            _LOGGER.error(f"Extreme temperature at hour {i}: {temps[i]}°C")
            return False
    
    return True


def validate_price_data(prices: List[float], max_hours: int) -> bool:
    """Validera prisdata (befintlig implementation)"""
    if not prices:
        return False
    
    check_hours = min(max_hours, len(prices))
    for i in range(check_hours):
        if prices[i] < MIN_REASONABLE_PRICE or prices[i] > MAX_REASONABLE_PRICE:
            _LOGGER.warning(f"Extreme price at hour {i}: {prices[i]}")
    
    return True


def check_future_warming_trend(temps: List[float], lookahead_hours: int) -> bool:
    """Kontrollera värmande trend (befintlig implementation)"""
    if len(temps) < 2:
        return False
    
    current_temp = temps[0]
    check_hours = min(lookahead_hours, len(temps) - 1)
    future_temps = temps[1:check_hours + 1]
    
    return all(temp >= current_temp for temp in future_temps)


def calculate_adjusted_thresholds(aggressiveness: float, max_price: float) -> Tuple[float, float]:
    """Beräkna justerade trösklar (befintlig implementation)"""
    aggressiveness = max(0.0, min(1.0, aggressiveness))
    
    adjusted_ratio = max(
        MIN_PRICE_THRESHOLD_RATIO,
        min(MAX_PRICE_THRESHOLD_RATIO,
            BASE_PRICE_THRESHOLD_RATIO - (aggressiveness * PREBOOST_AGGRESSIVENESS_SCALING_FACTOR))
    )
    
    price_threshold = max_price * adjusted_ratio
    return adjusted_ratio, price_threshold
