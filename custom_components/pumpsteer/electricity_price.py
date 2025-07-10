# electricity_price.py

import numpy as np
from typing import List, Dict, Optional
import logging

_LOGGER = logging.getLogger(__name__)

# Konstanter för bättre underhåll
DEFAULT_PERCENTILES = [20, 40, 60, 80]
DEFAULT_EXTREME_MULTIPLIER = 1.5
MIN_SAMPLES_FOR_CLASSIFICATION = 5

# Kategorier i ordning från billigast till dyrast
PRICE_CATEGORIES = [
    "extremt_billigt",
    "billigt", 
    "normalt",
    "dyrt",
    "extremt_dyrt"
]

def validate_price_list(price_list: List[float], min_samples: int = MIN_SAMPLES_FOR_CLASSIFICATION) -> bool:
    """
    Validerar att prislistan är giltig för analys.
    
    Args:
        price_list: Lista med elpriser
        min_samples: Minsta antal sampel som krävs
        
    Returns:
        True om listan är giltig, False annars
    """
    if not price_list or len(price_list) < min_samples:
        return False
    
    # Varna för negativa priser
    negative_prices = [p for p in price_list if p < 0]
    if negative_prices:
        _LOGGER.warning(f"Found {len(negative_prices)} negative prices in dataset")
    
    # Varna för extrema värden
    extreme_prices = [p for p in price_list if p > 10.0]  # > 10 kr/kWh är extremt
    if extreme_prices:
        _LOGGER.warning(f"Found {len(extreme_prices)} extremely high prices (>10 kr/kWh)")
    
    return True

def classify_prices(
    price_list: List[float], 
    percentiles: List[float] = None
) -> List[str]:
    """
    Tar en lista med timvisa elpriser och returnerar en lista med kategorier.
    
    Args:
        price_list: Lista med elpriser
        percentiles: Percentiler att använda för klassificering (default: [20, 40, 60, 80])
        
    Returns:
        Lista med kategorier: 'extremt_billigt', 'billigt', 'normalt', 'dyrt', 'extremt_dyrt'
    """
    if percentiles is None:
        percentiles = DEFAULT_PERCENTILES
        
    if not validate_price_list(price_list):
        _LOGGER.debug(f"Invalid price list for classification (length: {len(price_list) if price_list else 0})")
        return ["okänd"] * len(price_list) if price_list else []

    if len(percentiles) != 4:
        raise ValueError("Exactly 4 percentiles required for 5-category classification")

    thresholds = np.percentile(price_list, percentiles)
    categories = []

    for price in price_list:
        if price < thresholds[0]:
            categories.append(PRICE_CATEGORIES[0])  # extremt_billigt
        elif price < thresholds[1]:
            categories.append(PRICE_CATEGORIES[1])  # billigt
        elif price < thresholds[2]:
            categories.append(PRICE_CATEGORIES[2])  # normalt
        elif price < thresholds[3]:
            categories.append(PRICE_CATEGORIES[3])  # dyrt
        else:
            categories.append(PRICE_CATEGORIES[4])  # extremt_dyrt

    return categories


def get_daily_average(price_list: List[float]) -> float:
    """
    Returnerar medelvärdet för dagens elpriser.
    
    Args:
        price_list: Lista med elpriser
        
    Returns:
        Medelvärde, 0.0 om listan är tom
    """
    if not price_list:
        return 0.0
    return round(sum(price_list) / len(price_list), 3)


def get_price_statistics(price_list: List[float]) -> Dict[str, float]:
    """
    Returnerar grundläggande statistik för prislistan.
    
    Args:
        price_list: Lista med elpriser
        
    Returns:
        Dictionary med statistik (medel, median, min, max, std)
    """
    if not price_list:
        return {"average": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}
    
    return {
        "average": round(np.mean(price_list), 3),
        "median": round(np.median(price_list), 3),
        "min": round(min(price_list), 3),
        "max": round(max(price_list), 3),
        "std": round(np.std(price_list), 3)
    }


def is_extreme(
    price: float, 
    price_list: List[float], 
    multiplier: float = DEFAULT_EXTREME_MULTIPLIER
) -> bool:
    """
    Returnerar True om priset är extremt högt jämfört med dagsmedel.
    
    Args:
        price: Priset att kontrollera
        price_list: Lista med referenspriser
        multiplier: Multiplikator för vad som räknas som extremt (default: 1.5)
        
    Returns:
        True om priset är extremt högt
    """
    avg = get_daily_average(price_list)
    if avg == 0.0:
        return False
    return price > avg * multiplier


def count_categories(price_list: List[float]) -> Dict[str, int]:
    """
    Returnerar antal timmar för varje kategori.
    Effektivare än att anropa count_category() flera gånger.
    
    Args:
        price_list: Lista med elpriser
        
    Returns:
        Dictionary med antal för varje kategori
    """
    categories = classify_prices(price_list)
    counts = {category: 0 for category in PRICE_CATEGORIES}
    counts["okänd"] = 0
    
    for category in categories:
        counts[category] += 1
    
    return counts


def count_category(price_list: List[float], target_category: str) -> int:
    """
    Returnerar antal timmar som tillhör en viss kategori.
    
    Args:
        price_list: Lista med elpriser
        target_category: Kategori att räkna
        
    Returns:
        Antal timmar i kategorin
    """
    if target_category not in PRICE_CATEGORIES and target_category != "okänd":
        raise ValueError(f"Unknown category: {target_category}. Valid categories: {PRICE_CATEGORIES + ['okänd']}")
    
    categories = classify_prices(price_list)
    return categories.count(target_category)


def find_cheapest_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Hittar de billigaste timmarna i prislistan.
    
    Args:
        price_list: Lista med elpriser
        num_hours: Antal timmar att hitta
        
    Returns:
        Lista med index för de billigaste timmarna
    """
    if not price_list or num_hours <= 0:
        return []
    
    # Skapa lista med (index, pris) och sortera efter pris
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    indexed_prices.sort(key=lambda x: x[1])
    
    # Returnera de första num_hours indexen
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]


def find_most_expensive_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Hittar de dyraste timmarna i prislistan.
    
    Args:
        price_list: Lista med elpriser
        num_hours: Antal timmar att hitta
        
    Returns:
        Lista med index för de dyraste timmarna
    """
    if not price_list or num_hours <= 0:
        return []
    
    # Skapa lista med (index, pris) och sortera efter pris (fallande)
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    indexed_prices.sort(key=lambda x: x[1], reverse=True)
    
    # Returnera de första num_hours indexen
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]
