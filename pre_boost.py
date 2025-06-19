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
