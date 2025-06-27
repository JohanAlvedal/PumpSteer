import logging

_LOGGER = logging.getLogger(__name__)

def check_combined_preboost(temp_csv: str, prices: list[float],
                            lookahead_hours: int = 6,
                            cold_threshold: float = 2.0,
                            price_threshold_ratio: float = 0.8,
                            min_peak_hits: int = 1,
                            aggressiveness: float = 0.0,
                            inertia: float = 1.0) -> str | None:
    """
    Returnerar 'preboost' om vi ska 'gasa' vid en förväntad kall och dyr period.
    Detta är en framåtblickande funktion.
    """
    try:
        temps = [float(t.strip()) for t in temp_csv.split(",") if t.strip() != ""]
        if not temps or not prices or len(temps) < lookahead_hours or len(prices) < lookahead_hours:
            _LOGGER.debug("Pre-boost check: Inte tillräckligt med data (temps: %d, prices: %d)", len(temps), len(prices))
            return None
    except Exception:
        _LOGGER.error("Pre-boost check: Fel vid bearbetning av data", exc_info=True)
        return None

    # Använd aggressiveness för att justera pris-tröskeln för att förhindra preboost
    # En högre aggressivitet gör det svårare att pre-boosta på pris (höjer tröskeln)
    adjusted_price_threshold_ratio = max(0.5, min(0.9, 0.9 - (aggressiveness * 0.04)))
    max_price = max(prices[:lookahead_hours])
    price_threshold = max_price * adjusted_price_threshold_ratio

    # Huvudlogik för pre-boost: Söker efter en framtida kall och dyr timme
    lead_time = min(3.0, max(0.5, inertia * 0.75))
    lead_hours = int(round(lead_time))

    for i in range(1, lookahead_hours):
        # Kollar om framtida timmar är både kalla och dyra
        if temps[i] < cold_threshold and prices[i] >= price_threshold:
            if i <= lead_hours:
                _LOGGER.debug(f"PREBOOST: Preboost aktiveras (inertia: {inertia:.2f}, lead_hours: {lead_hours}, peak om {i}h)")
                return "preboost"
            else:
                _LOGGER.debug(f"PREBOOST: För tidigt att preboosta (peak om {i}h, lead_hours: {lead_hours})")
                return None

    _LOGGER.debug("Preboost: Inga kall+dyra timmar inom prognosen.")
    return None
