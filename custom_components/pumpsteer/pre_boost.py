import logging

_LOGGER = logging.getLogger(__name__)  # Hämta samma logger som används i andra filer

def check_combined_preboost(temp_csv: str, prices: list[float],
                            lookahead_hours: int = 6,
                            cold_threshold: float = 2.0,
                            price_threshold_ratio: float = 0.8,
                            min_peak_hits: int = 1) -> bool:
    """
    Returnerar True om vi förväntar oss minst `min_peak_hits` timmar
    där temperaturen är kall OCH elpriset är högt under lookahead-perioden.

    Args:
        temp_csv (str): Kommaseparerade temperaturprognoser (timmar).
        prices (List[float]): Prisprognos för kommande timmar.
        lookahead_hours (int): Antal timmar att analysera framåt.
        cold_threshold (float): Temperaturgräns för att anse det "kallt".
        price_threshold_ratio (float): Procent av maxpris som räknas som "högt pris".
        min_peak_hits (int): Minsta antal samtidiga kall/dyr timmar som krävs.
import logging

_LOGGER = logging.getLogger(__name__)

def check_combined_preboost(temp_csv: str, prices: list[float],
                            lookahead_hours: int = 6,
                            cold_threshold: float = 2.0,
                            price_threshold_ratio: float = 0.8,
                            min_peak_hits: int = 1,
                            aggressiveness: float = 0.0) -> str | None:
    """
    Returnerar 'preboost' om vi ska 'gasa', 'braking' om vi ska 'bromsa', eller None.
    
    'preboost' aktiveras om det finns en kombination av kallt/dyrt i framtiden (inte den aktuella timmen).
    'braking' aktiveras om den aktuella timmen är kall och dyr.
    """
    try:
        temps = [float(t.strip()) for t in temp_csv.split(",") if t.strip() != ""]
        if not temps or not prices or len(temps) < lookahead_hours or len(prices) < lookahead_hours:
            _LOGGER.debug("Pre-boost check: Inte tillräckligt med data för prognos (temps: %d, prices: %d).", len(temps), len(prices))
            return None # Inte tillräckligt med data
    except Exception:
        _LOGGER.error("Pre-boost check: Fel vid bearbetning av prognosdata.", exc_info=True)
        return None

    # Justera pris-tröskeln baserat på aggressivitet
    # En högre aggressivitet sänker pritröskeln, vilket gör det lättare
    # att trigga pre-boost på mindre prishöjningar.
    adjusted_price_threshold_ratio = 0.9 - (aggressiveness * 0.04)
    # Säkerställ att ratio håller sig inom rimliga gränser
    adjusted_price_threshold_ratio = max(0.5, min(0.9, adjusted_price_threshold_ratio))
    
    max_price = max(prices[:lookahead_hours])
    price_threshold = max_price * adjusted_price_threshold_ratio
    
    _LOGGER.debug(f"Pre-boost check: Aggressiveness={aggressiveness:.1f}, Adjusted price ratio={adjusted_price_threshold_ratio:.2f}, Price threshold={price_threshold:.2f}")

    # --- NY LOGIK FÖR BROMSSIGNAL UNDER PRISTOPPEN (aktuell timme) ---
    # Om den aktuella timmen (index 0) är kall OCH dyr.
    if temps[0] < cold_threshold and prices[0] >= price_threshold:
        _LOGGER.info(f"Pre-boost check: Aktiverar BROMSSIGNAL för aktuell timme (Temp: {temps[0]:.1f}°C, Pris: {prices[0]:.2f} > {price_threshold:.2f}).")
        return "braking" # Signalera att vi ska bromsa NU.

    # --- KONTROLL FÖR PREBOOST (LADDNING) INFÖR TOPPEN (kommande timmar) ---
    # Titta på de kommande timmarna (från index 1 till lookahead_hours-1).
    cold_and_expensive_future_hours = 0
    for i in range(1, lookahead_hours): # Börjar från nästa timme (index 1)
        if temps[i] < cold_threshold and prices[i] >= price_threshold:
            cold_and_expensive_future_hours += 1

    if cold_and_expensive_future_hours >= min_peak_hits:
        _LOGGER.info(f"Pre-boost check: Aktiverar PREBOOST-läge för kommande dyra timmar ({cold_and_expensive_future_hours} träffar).")
        return "preboost" # Signalera att vi ska gasa INFÖR toppen.

    # Om ingen av ovanstående villkor är uppfyllda
    _LOGGER.debug("Pre-boost check: Inga preboost- eller bromsvillkor uppfyllda.")
    return None


    Returns:
        bool: True om preboost bör aktiveras.
    """
    try:
        temps = [float(t.strip()) for t in temp_csv.split(",") if t.strip() != ""]
        if len(temps) < lookahead_hours or len(prices) < lookahead_hours:
            _LOGGER.warning(f"PreBoost: Inte tillräckligt med data. temp_len={len(temps)}, prices_len={len(prices)}, lookahead_hours={lookahead_hours}")
            return False
    except Exception as e:
        _LOGGER.error(f"PreBoost: Fel vid bearbetning av temperaturer: {e}")
        return False

    max_price = max(prices[:lookahead_hours])
    price_threshold = max_price * price_threshold_ratio

    _LOGGER.debug(f"PreBoost: lookahead_hours={lookahead_hours}, cold_threshold={cold_threshold}, price_threshold={price_threshold}, max_price={max_price}")

    peak_hits = 0
    hit_hours = []  # Lista för att hålla reda på vilka timmar som räknades som peak hits
    for i in range(min(lookahead_hours, len(temps), len(prices))):
        is_cold = temps[i] <= cold_threshold
        is_expensive = prices[i] >= price_threshold
        _LOGGER.debug(f"PreBoost: Timme {i}: temp={temps[i]}, price={prices[i]}, is_cold={is_cold}, is_expensive={is_expensive}")
        if is_cold and is_expensive:
            peak_hits += 1
            hit_hours.append(i)
            _LOGGER.info(f"PreBoost: Timme {i} räknas som peak hit (temp={temps[i]}, price={prices[i]})")
        if peak_hits >= min_peak_hits:
            _LOGGER.info(f"PreBoost: Pre-boost aktiverat. Peak hits uppnåddes efter {peak_hits} timmar: {hit_hours}")
            return True

    _LOGGER.info(f"PreBoost: Pre-boost inte aktiverat. Peak hits={peak_hits}, min_peak_hits={min_peak_hits}")
    return False

# def check_combined_preboost(temp_csv: str, prices: list[float],
#                             lookahead_hours: int = 6,
#                             cold_threshold: float = 2.0,
#                             price_threshold_ratio: float = 0.8,
#                             min_peak_hits: int = 1) -> bool:
#     """
#     Returnerar True om vi förväntar oss minst `min_peak_hits` timmar
#     där temperaturen är kall OCH elpriset är högt under lookahead-perioden.

#     Args:
#         temp_csv (str): Kommaseparerade temperaturprognoser (timmar).
#         prices (List[float]): Prisprognos för kommande timmar.
#         lookahead_hours (int): Antal timmar att analysera framåt.
#         cold_threshold (float): Temperaturgräns för att anse det "kallt".
#         price_threshold_ratio (float): Procent av maxpris som räknas som "högt pris".
#         min_peak_hits (int): Minsta antal samtidiga kall/dyr timmar som krävs.

#     Returns:
#         bool: True om preboost bör aktiveras.
#     """
#     try:
#         temps = [float(t.strip()) for t in temp_csv.split(",") if t.strip() != ""]
#         if len(temps) < lookahead_hours or len(prices) < lookahead_hours:
#             return False
#     except Exception:
#         return False

#     max_price = max(prices[:lookahead_hours])
#     price_threshold = max_price * price_threshold_ratio

#     peak_hits = 0
#     for i in range(min(lookahead_hours, len(temps), len(prices))):
#         if temps[i] <= cold_threshold and prices[i] >= price_threshold:
#             peak_hits += 1
#         if peak_hits >= min_peak_hits:
#             return True

#     return False
