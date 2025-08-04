# Fil: pre_boost.py - Förbättrad timing-logik
import logging
from typing import Optional, List, Tuple

from .settings import (
    PREBOOST_AGGRESSIVENESS_SCALING_FACTOR,
    MIN_PRICE_THRESHOLD_RATIO,
    MAX_PRICE_THRESHOLD_RATIO,
    BASE_PRICE_THRESHOLD_RATIO,
    MAX_PREBOOST_HOURS,
    PREBOOST_TEMP_THRESHOLD,
    # Nya konstanter från settings
    PREBOOST_MIN_ADVANCE_FACTOR,
    PREBOOST_MAX_ADVANCE_FACTOR,
    PREBOOST_MIN_ADVANCE_HOURS,
    PREBOOST_MAX_ADVANCE_HOURS,
    SEVERITY_ADJUSTMENT_FACTOR,
    MIN_REASONABLE_TEMP,
    MAX_REASONABLE_TEMP,
    MIN_REASONABLE_PRICE,
    MAX_REASONABLE_PRICE,
)

_LOGGER = logging.getLogger(__name__)


def calculate_optimal_preboost_timing(
    inertia: float, 
    peak_severity: float = 1.0
) -> Tuple[float, float]:
    """
    Beräkna optimal pre-boost timing window baserat på hus-inertia och peak-svårighetsgrad.
    
    Args:
        inertia: Systemtröghet (högre = mer förhandstid behövs)
        peak_severity: Svårighetsgrad för peak (1.0 = normal, >1.0 = svårare)
        
    Returns:
        Tuple med (min_advance_hours, max_advance_hours)
    """
    # Säkerställ rimlig inertia
    inertia = max(0.5, min(5.0, inertia))
    peak_severity = max(0.5, min(3.0, peak_severity))
    
    # Grundläggande timing baserat på inertia
    base_min = inertia * PREBOOST_MIN_ADVANCE_FACTOR
    base_max = inertia * PREBOOST_MAX_ADVANCE_FACTOR
    
    # Justera för peak-svårighetsgrad (svårare peaks = tidigare start)
    severity_adjustment = (peak_severity - 1.0) * SEVERITY_ADJUSTMENT_FACTOR
    
    min_advance = max(PREBOOST_MIN_ADVANCE_HOURS, base_min + severity_adjustment)
    max_advance = min(PREBOOST_MAX_ADVANCE_HOURS, base_max + severity_adjustment)
    
    # Säkerställ logisk ordning
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
    """
    Beräkna svårighetsgrad för en cold+expensive peak.
    
    Args:
        temp_drop: Hur många grader kallare än threshold
        price_ratio: Priset som andel av max pris (0.0-1.0)
        duration_hours: Hur länge peak:en varar
        
    Returns:
        Severity score (1.0 = normal, >1.0 = svårare)
    """
    # Temperatur-komponenten (större drop = svårare)
    temp_severity = min(2.0, abs(temp_drop) / 3.0)  # Normalisera till 0-2
    
    # Pris-komponenten (högre pris = svårare)
    price_severity = min(2.0, (price_ratio - 0.7) / 0.2)  # >70% av max = svårt
    
    # Varaktighets-komponenten (längre = svårare)
    duration_severity = min(1.5, duration_hours / 3.0)
    
    # Kombinera komponenterna
    total_severity = 1.0 + (temp_severity + price_severity + duration_severity) / 3.0
    
    return max(0.5, min(3.0, total_severity))


def find_cold_expensive_peaks(
    temps: List[float], 
    prices: List[float], 
    cold_threshold: float,
    price_threshold: float,
    max_hours: int
) -> List[Tuple[int, float, float]]:
    """
    Hitta alla cold+expensive peaks inom tidsramen.
    
    Args:
        temps: Temperaturlista
        prices: Prislista
        cold_threshold: Temperaturtröskel
        price_threshold: Priströskel
        max_hours: Max timmar att analysera
        
    Returns:
        Lista med (hour_index, severity, combined_score) för varje peak
    """
    peaks = []
    max_price = max(prices[:max_hours]) if prices else 1.0
    
    check_hours = min(max_hours, len(temps), len(prices))
    
    for i in range(1, check_hours):
        temp = temps[i]
        price = prices[i]
        
        is_cold = temp < cold_threshold
        is_expensive = price >= price_threshold
        
        if is_cold and is_expensive:
            # Beräkna severity för denna peak
            temp_drop = cold_threshold - temp
            price_ratio = price / max_price if max_price > 0 else 0.5
            
            # Kolla om peak:en fortsätter nästa timme (duration)
            duration = 1
            for j in range(i + 1, min(i + 4, check_hours)):  # Max 3h framåt
                if j < len(temps) and j < len(prices):
                    if temps[j] < cold_threshold and prices[j] >= price_threshold:
                        duration += 1
                    else:
                        break
            
            severity = calculate_peak_severity(temp_drop, price_ratio, duration)
            combined_score = temp_drop * price_ratio * duration  # För sortering
            
            peaks.append((i, severity, combined_score))
            
            _LOGGER.debug(
                f"Peak found at hour {i}: temp={temp:.1f}°C (drop: {temp_drop:.1f}), "
                f"price={price:.3f} (ratio: {price_ratio:.2f}), duration={duration}h, "
                f"severity={severity:.2f}"
            )
    
    # Sortera peaks efter combined_score (svåraste först)
    peaks.sort(key=lambda x: x[2], reverse=True)
    
    return peaks


def check_combined_preboost(
    temp_csv: str,
    prices: List[float],
    lookahead_hours: int = MAX_PREBOOST_HOURS,
    cold_threshold: float = PREBOOST_TEMP_THRESHOLD,
    price_threshold_ratio: float = 0.8,  # Behålls för bakåtkompatibilitet
    min_peak_hits: int = 1,  # Behålls för bakåtkompatibilitet
    aggressiveness: float = 0.0,
    inertia: float = 1.0
) -> Optional[str]:
    """
    FÖRBÄTTRAD pre-boost kontroll med optimal timing.
    
    Letar efter cold+expensive peaks och aktiverar pre-boost vid optimal timing
    baserat på hus-inertia och peak-svårighetsgrad.
    """
    _LOGGER.debug(
        f"Pre-boost check (IMPROVED): lookahead={lookahead_hours}h, "
        f"cold_threshold={cold_threshold}°C, aggressiveness={aggressiveness:.2f}, "
        f"inertia={inertia:.2f}"
    )
    
    # Parsa temperaturdata (använd befintlig funktion)
    temps = parse_temperature_csv_safe(temp_csv)
    if temps is None:
        return None
    
    # Validera data tillgänglighet
    if len(temps) < lookahead_hours or (prices and len(prices) < lookahead_hours):
        original_lookahead = lookahead_hours
        lookahead_hours = min(len(temps), len(prices) if prices else len(temps))
        _LOGGER.debug(f"Adjusting lookahead: {original_lookahead}h → {lookahead_hours}h")
        
        if lookahead_hours < 2:  # Behöver minst 2h för meningsfull analys
            _LOGGER.warning("Insufficient data for meaningful pre-boost analysis")
            return None
    
    # Validera data kvalitet
    if not validate_temperature_data(temps, lookahead_hours):
        return None
    if not validate_price_data(prices, lookahead_hours):
        return None
    
    # Kontrollera värmande trend (befintlig logik)
    if check_future_warming_trend(temps, lookahead_hours):
        _LOGGER.debug("Pre-boost: Skipping due to warming trend")
        return None
    
    # Beräkna priströsklar
    max_price = max(prices[:lookahead_hours]) if prices else 0.0
    if max_price <= 0:
        _LOGGER.warning("Invalid max price for pre-boost analysis")
        return None
    
    adjusted_ratio, price_threshold = calculate_adjusted_thresholds(aggressiveness, max_price)
    
    # FÖRBÄTTRAT: Hitta alla peaks med severity
    peaks = find_cold_expensive_peaks(
        temps, prices, cold_threshold, price_threshold, lookahead_hours
    )
    
    if not peaks:
        _LOGGER.debug("No cold+expensive peaks found in forecast")
        return None
    
    # Analysera varje peak för optimal timing
    for peak_hour, severity, combined_score in peaks:
        hours_to_peak = peak_hour  # Timmar från nu till peak
        
        # FÖRBÄTTRAT: Beräkna optimal timing för denna peak
        min_advance, max_advance = calculate_optimal_preboost_timing(inertia, severity)
        
        _LOGGER.debug(
            f"Peak at hour {peak_hour}: severity={severity:.2f}, "
            f"optimal advance: {min_advance:.1f}-{max_advance:.1f}h, "
            f"actual: {hours_to_peak}h"
        )
        
        # Kontrollera om vi är i optimal timing-window
        if min_advance <= hours_to_peak <= max_advance:
            _LOGGER.info(
                f"PREBOOST ACTIVATED (OPTIMAL TIMING): Peak in {hours_to_peak}h "
                f"(optimal: {min_advance:.1f}-{max_advance:.1f}h), "
                f"severity: {severity:.2f}, temp: {temps[peak_hour]:.1f}°C, "
                f"price: {prices[peak_hour]:.3f}"
            )
            return "preboost"
        
        elif hours_to_peak > max_advance:
            _LOGGER.debug(
                f"Peak too far away: {hours_to_peak:.1f}h > {max_advance:.1f}h "
                f"(will check again later)"
            )
            # Fortsätt att kolla andra peaks
            continue
            
        elif hours_to_peak < min_advance:
            _LOGGER.debug(
                f"Peak too close for optimal pre-boost: {hours_to_peak:.1f}h < {min_advance:.1f}h "
                f"(should have started earlier)"
            )
            # För sent för denna peak, fortsätt kolla andra
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
