from datetime import datetime, timedelta
from .settings import (
    HIGH_PRICE_THRESHOLD,
    DEFAULT_HOUSE_INERTIA,
)

_LOGGER = logging.getLogger(__name__)

def get_preboost_strategy(price_forecast, temp_forecast, current_hour, house_inertia=None):
    if house_inertia is None:
        house_inertia = DEFAULT_HOUSE_INERTIA

    cold_and_expensive_hours = []
    for hour_offset in range(24):
        forecast_hour = current_hour + timedelta(hours=hour_offset)
        price = price_forecast.get(hour_offset)
        temp = temp_forecast.get(hour_offset)

        if price is None or temp is None:
            continue

        if price >= HIGH_PRICE_THRESHOLD and temp < 18:  # <– 18 är fortfarande hårdkodad, kan flyttas till settings
            cold_and_expensive_hours.append(forecast_hour)

    first_preboost_hour = (
        cold_and_expensive_hours[0] - timedelta(hours=house_inertia)
        if cold_and_expensive_hours else None
    )

    strategy = {
        "cold_and_expensive_hours_next_6h": [
            hour for hour in cold_and_expensive_hours
            if current_hour <= hour <= current_hour + timedelta(hours=6)
        ],
        "first_preboost_hour": first_preboost_hour,
        "preboost_expected_in_hours": (
            (first_preboost_hour - current_hour).total_seconds() / 3600
            if first_preboost_hour else None
        ),
    }

    _LOGGER.debug("Preboost-strategi beräknad: %s", strategy)
    return strategy
