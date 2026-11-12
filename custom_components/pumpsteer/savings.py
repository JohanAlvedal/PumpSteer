"""Estimated load-shifting value for PumpSteer.

Purely observational: nothing in this module is read by the control loop.

Model (deliberately simple and locally explainable):

    offset_c   = fake_temp - fake_temp_without_price_logic
                 (positive while braking, negative while preheating)
    delta_kwh  = kwh_per_c_hour * offset_c * dt_hours
                 (electric energy the heat pump is assumed NOT to use)
    value      = delta_kwh * (price_now - reference_price)

The reference price is today's mean price. The model assumes every braked kWh
is bought back later at the reference price and every preheated kWh replaces
one that would otherwise have been bought at the reference price. It therefore
values only the *shift* in time, never a reduction in total heat, which keeps
the estimate conservative.

It is an estimate, not a measurement: nobody can observe the same day without
PumpSteer. kwh_per_c_hour is a user-tunable assumption about the house and the
heat pump (electric kWh per °C of outdoor-signal offset per hour).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

# Long gaps (restarts, outages) must not be credited as one long sample.
MAX_SAMPLE_SECONDS: float = 300.0

# Rough default: a house losing ~200 W/K with a heat pump COP of ~3 needs
# about 0.07 kWh of electricity per °C and hour. Users should tune it.
DEFAULT_KWH_PER_C_HOUR: float = 0.07
MIN_KWH_PER_C_HOUR: float = 0.0
MAX_KWH_PER_C_HOUR: float = 1.0


def savings_signal(entry_id: str) -> str:
    """Dispatcher signal carrying SavingsSample objects for one entry."""
    return f"pumpsteer_{entry_id}_savings_sample"


@dataclass(frozen=True)
class SavingsSample:
    """One control-cycle observation sent from the controller."""

    now: datetime
    offset_c: float
    price: float | None
    reference_price: float | None
    kwh_per_c_hour: float


@dataclass
class SavingsEstimator:
    """Accumulates estimated value of shifted heating energy."""

    total: float = 0.0
    reduced_kwh: float = 0.0
    added_kwh: float = 0.0
    last_t: datetime | None = field(default=None)

    def update(self, sample: SavingsSample) -> float:
        """Integrate one sample and return the value added by it."""
        previous = self.last_t
        self.last_t = sample.now
        if previous is None:
            return 0.0

        dt_s = (sample.now - previous).total_seconds()
        if dt_s <= 0:
            return 0.0
        dt_s = min(dt_s, MAX_SAMPLE_SECONDS)

        values = (
            sample.offset_c,
            sample.price,
            sample.reference_price,
            sample.kwh_per_c_hour,
        )
        if any(v is None or not math.isfinite(v) for v in values):
            return 0.0
        k = min(max(sample.kwh_per_c_hour, MIN_KWH_PER_C_HOUR), MAX_KWH_PER_C_HOUR)
        if k == 0.0 or sample.offset_c == 0.0:
            return 0.0

        delta_kwh = k * sample.offset_c * dt_s / 3600.0
        if delta_kwh > 0:
            self.reduced_kwh += delta_kwh
        else:
            self.added_kwh += -delta_kwh

        value = delta_kwh * (sample.price - sample.reference_price)
        self.total += value
        return value


def price_scale_to_currency(unit: str | None) -> float:
    """Return the factor that converts the price unit to main currency/kWh.

    Prices in öre or cents (sub-units) are divided by 100.
    """
    if not unit:
        return 1.0
    head = unit.split("/")[0].strip().lower()
    if head in {"öre", "ore", "cent", "cents", "c", "ct", "øre"}:
        return 0.01
    return 1.0
