"""Validation helpers for the PumpSteer V3 domain boundary."""

from __future__ import annotations

import math
from datetime import datetime
from numbers import Real

from .enums import Unit


def finite_float(value: Real, field_name: str) -> float:
    """Return a finite float or raise a field-specific error."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def aware_datetime(value: datetime, field_name: str) -> datetime:
    """Require a timezone-aware timestamp with a usable UTC offset."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def supported_unit(value: Unit | str, field_name: str = "unit") -> Unit:
    """Normalize a unit while rejecting implicit unit conversion."""
    try:
        return Unit(value)
    except (TypeError, ValueError) as err:
        supported = ", ".join(unit.value for unit in Unit)
        raise ValueError(f"{field_name} must be one of: {supported}") from err
