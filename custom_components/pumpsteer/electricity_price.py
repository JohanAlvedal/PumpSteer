# electricity_price.py

import numpy as np

def classify_prices(price_list):
    """
    Tar en lista med timvisa elpriser och returnerar en lista med kategorier:
    'extremt_billigt', 'billigt', 'normalt', 'dyrt', 'extremt_dyrt'
    """
    if not price_list or len(price_list) < 5:
        return ["okänd"] * len(price_list)

    thresholds = np.percentile(price_list, [20, 40, 60, 80])
    categories = []

    for price in price_list:
        if price < thresholds[0]:
            categories.append("extremt_billigt")
        elif price < thresholds[1]:
            categories.append("billigt")
        elif price < thresholds[2]:
            categories.append("normalt")
        elif price < thresholds[3]:
            categories.append("dyrt")
        else:
            categories.append("extremt_dyrt")

    return categories


def get_daily_average(price_list):
    """
    Returnerar medelvärdet för dagens elpriser.
    """
    if not price_list:
        return 0.0
    return round(sum(price_list) / len(price_list), 3)


def is_extreme(price, price_list, multiplier=1.5):
    """
    Returnerar True om priset är extremt högt jämfört med dagsmedel.
    """
    avg = get_daily_average(price_list)
    return price > avg * multiplier


def count_category(price_list, target_category):
    """
    Returnerar antal timmar som tillhör en viss kategori.
    """
    categories = classify_prices(price_list)
    return categories.count(target_category)
