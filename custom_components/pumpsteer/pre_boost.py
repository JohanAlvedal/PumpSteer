# Fil: pre_boost.py
import logging
from typing import Optional

from .settings import (
    PREBOOST_AGGRESSIVENESS_SCALING_FACTOR,
    INERTIA_LEAD_TIME_FACTOR,
    MIN_PRICE_THRESHOLD_RATIO,
    MAX_PRICE_THRESHOLD_RATIO,
    BASE_PRICE_THRESHOLD_RATIO,
    MIN_LEAD_TIME,
    MAX_LEAD_TIME,
    MAX_PREBOOST_HOURS, # Ny import
    PREBOOST_TEMP_THRESHOLD, # Ny import
)

_LOGGER = logging.getLogger(__name__)

def check_combined_preboost(
    temp_csv: str,
    prices: list[float],
    lookahead_hours: int = MAX_PREBOOST_HOURS, # Använd konstant från settings
    cold_threshold: float = 2.0, # Denna kommer att justeras i sensor.py
    price_threshold_ratio: float = 0.8,
    min_peak_hits: int = 1, # Fortfarande oanvänd
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
        # Konvertera komma-separerad sträng till en lista med floats.
        # Hoppa över tomma strängar om det finns dubbla kommatecken eller inledande/avslutande kommatecken.
        temps = [float(t.strip()) for t in temp_csv.split(",") if t.strip()]

        if not temps:
            _LOGGER.warning("Pre-boost check: Received empty or invalid temperature forecast CSV. Skipping pre-boost.")
            return None

        # Kontrollerar att vi har tillräckligt med data för lookahead_hours
        if len(temps) < lookahead_hours or (prices and len(prices) < lookahead_hours):
            # Anpassa lookahead_hours om vi inte har tillräckligt med data
            original_lookahead = lookahead_hours
            lookahead_hours = min(len(temps), len(prices) if prices else 0)
            _LOGGER.debug(
                "Pre-boost check: Not enough data for requested lookahead_hours (%d). "
                "Adjusting to available data: %d hours (temps: %d, prices: %d).",
                original_lookahead, lookahead_hours, len(temps), (len(prices) if prices else 0)
            )
            if lookahead_hours == 0:
                _LOGGER.warning("Pre-boost check: No valid temperature or price data available. Skipping pre-boost.")
                return None

    except ValueError:
        _LOGGER.error("Pre-boost check: Invalid number format in temperature forecast CSV: '%s'. Skipping pre-boost.", temp_csv, exc_info=True)
        return None
    except Exception as e:
        _LOGGER.error("Pre-boost check: Unexpected error processing temperature data: %s. Skipping pre-boost.", e, exc_info=True)
        return None

    # Undvik preboost om det inte blir kallare än nu inom lookahead_hours
    # Se till att temps har tillräckligt med element
    if len(temps) > 0 and all(temps[i] >= temps[0] for i in range(1, min(lookahead_hours, len(temps)))):
        _LOGGER.debug(
            "Pre-boost avbryts – framtida temperaturer är lika eller varmare än nu (nu: %.1f°C, framtid: %s)",
            temps[0],
            ", ".join([f"{t:.1f}" for t in temps[1:min(lookahead_hours, len(temps))]])
        )
        return None

    # Input validation för priser och temperaturer inom det relevanta intervallet
    if any(p < 0 for p in prices[:lookahead_hours]):
        _LOGGER.warning("Pre-boost check: Negative prices detected in forecast within lookahead_hours.")

    if any(t < -50 or t > 50 for t in temps[:lookahead_hours]):
        _LOGGER.warning("Pre-boost check: Extreme temperatures detected in forecast within lookahead_hours.")

    # Använd aggressiveness för att justera pris-tröskeln för att aktivera preboost
    # Högre aggressiveness gör det svårare att preboosta baserat på pris (höjer tröskeln)
    adjusted_price_threshold_ratio = max(
        MIN_PRICE_THRESHOLD_RATIO,
        min(MAX_PRICE_THRESHOLD_RATIO,
            BASE_PRICE_THRESHOLD_RATIO - (aggressiveness * PREBOOST_AGGRESSIVENESS_SCALING_FACTOR))
    )

    max_price = max(prices[:lookahead_hours]) if prices else 0.0 # Säkerställ hantering av tomma priser
    price_threshold = max_price * adjusted_price_threshold_ratio

    # Beräkna ledtid baserat på systemets tröghet (inertia)
    lead_time = min(MAX_LEAD_TIME, max(MIN_LEAD_TIME, inertia * INERTIA_LEAD_TIME_FACTOR))
    lead_hours = int(round(lead_time))

    _LOGGER.debug(
        "Pre-boost parameters: aggressiveness=%.2f, adjusted_threshold_ratio=%.2f, "
        "price_threshold=%.2f, inertia=%.2f, lead_hours=%d",
        aggressiveness, adjusted_price_threshold_ratio, price_threshold, inertia, lead_hours
    )

    # Huvudlogik för pre-boost: Leta efter en framtida timme som är både kall och dyr
    # Säkerställ att vi inte går utanför någon av listorna
    max_safe_hours = min(lookahead_hours, len(temps) - 1, len(prices) - 1)
    if max_safe_hours < 1:  # Behöver minst 1 timme att kolla
        _LOGGER.debug("Pre-boost check: Not enough data points for lookahead")
        return None
    
    for i in range(1, max_safe_hours + 1):
        # Kontrollera om framtida timmar är både kalla och dyra
        # cold_threshold bör komma från sensor.py och baseras på target_temp
        if temps[i] < cold_threshold and prices[i] >= price_threshold:
            _LOGGER.debug(
                "Pre-boost check: Found cold+expensive period at hour %d (temp=%.1f°C, price=%.2f)",
                i, temps[i], prices[i]
            )

            # Om den kalla/dyra perioden är inom vår ledtid, aktivera preboost
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
                # Eftersom det är för tidigt att preboosta nu, men vi hittade en matchning,
                # returnerar vi None så att den inte aktiveras.
                return None

    _LOGGER.debug("Pre-boost check: No suitable cold+expensive hours found within the forecast for pre-boost.")
    return None
