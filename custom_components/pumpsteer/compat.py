"""Compatibility helpers for optional utilities."""

from typing import Sequence, Any

from . import utils as _utils

__all__ = ["detect_price_interval_minutes"]


def _fallback_detect_price_interval_minutes(prices: Sequence[Any]) -> int:
    """Infer the resolution of a price list when utils lacks the helper."""
    if not prices:
        return 60

    length = len(prices)
    if length <= 0:
        return 60

    if 1440 % length == 0:
        return max(1, 1440 // length)

    for multiplier in range(2, 8):
        if length % multiplier == 0:
            base = length // multiplier
            if base > 0 and 1440 % base == 0:
                return max(1, 1440 // base)

    return 60


def detect_price_interval_minutes(prices: Sequence[Any]) -> int:
    """Return the bundled helper or fall back to a local implementation."""
    helper = getattr(_utils, "detect_price_interval_minutes", None)
    if callable(helper):
        return helper(prices)
    return _fallback_detect_price_interval_minutes(prices)
