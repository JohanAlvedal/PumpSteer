"""Map one user saving preference to fixed internal price percentiles.

This module classifies economic intent only. It neither consumes prices nor
grants planning, model, or physical-control authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_SAVING_LEVEL = 0
MAX_SAVING_LEVEL = 5
DEFAULT_SAVING_LEVEL = 3

_PERCENTILES: tuple[tuple[int, int] | None, ...] = (
    None,
    (20, 90),
    (25, 85),
    (30, 80),
    (35, 70),
    (40, 60),
)


@dataclass(frozen=True, slots=True)
class PriceBandPolicy:
    """Derived price-band intent with no controller authority."""

    saving_level: int
    classification_enabled: bool
    cheap_percentile: int | None
    expensive_percentile: int | None

    def __post_init__(self) -> None:
        level = normalize_saving_level(self.saving_level)
        object.__setattr__(self, "saving_level", level)
        if not isinstance(self.classification_enabled, bool):
            raise TypeError("classification_enabled must be a boolean")
        expected = _PERCENTILES[level]
        if expected is None:
            if self.classification_enabled:
                raise ValueError("level 0 classification must be disabled")
            if (
                self.cheap_percentile is not None
                or self.expensive_percentile is not None
            ):
                raise ValueError("disabled classification cannot have percentiles")
            return
        if not self.classification_enabled:
            raise ValueError("levels 1 to 5 require classification")
        for name in ("cheap_percentile", "expensive_percentile"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
        if self.cheap_percentile >= self.expensive_percentile:
            raise ValueError("cheap_percentile must be below expensive_percentile")
        if (self.cheap_percentile, self.expensive_percentile) != expected:
            raise ValueError("percentiles must match the saving-level policy")


def normalize_saving_level(value: object) -> int:
    """Return an exact integer saving level in the supported range."""
    if isinstance(value, bool):
        raise TypeError("saving_level must be numeric")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as err:
        raise TypeError("saving_level must be numeric") from err
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError("saving_level must be a finite whole number")
    result = int(numeric)
    if not MIN_SAVING_LEVEL <= result <= MAX_SAVING_LEVEL:
        raise ValueError("saving_level must be between 0 and 5")
    return result


def price_policy_for_saving_level(value: object) -> PriceBandPolicy:
    """Derive the complete classification policy from one user preference."""
    level = normalize_saving_level(value)
    percentiles = _PERCENTILES[level]
    if percentiles is None:
        return PriceBandPolicy(
            saving_level=level,
            classification_enabled=False,
            cheap_percentile=None,
            expensive_percentile=None,
        )
    cheap, expensive = percentiles
    return PriceBandPolicy(
        saving_level=level,
        classification_enabled=True,
        cheap_percentile=cheap,
        expensive_percentile=expensive,
    )
