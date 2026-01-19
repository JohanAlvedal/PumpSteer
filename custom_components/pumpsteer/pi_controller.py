from __future__ import annotations

from statistics import median
from typing import List, Tuple


def select_price_horizon(dt_minutes: int, horizon_15m: int, horizon_hourly: int) -> int:
    """Select horizon steps based on price resolution."""
    if dt_minutes > 0 and dt_minutes <= 30:
        return horizon_15m
    return horizon_hourly


def compute_price_baseline(
    prices: List[float], start_index: int, window_steps: int
) -> float:
    """Compute a median baseline from the upcoming price window."""
    if not prices or start_index >= len(prices):
        return 0.0
    window = prices[start_index : min(len(prices), start_index + window_steps)]
    return float(median(window)) if window else float(prices[start_index])


def compute_price_pressure(
    prices: List[float], start_index: int, horizon_steps: int, baseline: float
) -> float:
    """Compute a weighted positive price pressure over the horizon."""
    if not prices or horizon_steps <= 0 or start_index >= len(prices):
        return 0.0

    horizon = min(horizon_steps, len(prices) - start_index)
    total = 0.0
    for offset in range(horizon):
        price = prices[start_index + offset]
        weight = (horizon_steps - offset) / horizon_steps
        total += weight * max(price - baseline, 0.0)
    return total


def update_pi_output(
    value: float,
    integral: float,
    kp: float,
    ki: float,
    dt_hours: float,
    output_min: float,
    output_max: float,
) -> Tuple[float, float, bool, bool]:
    """Update PI output with basic anti-windup."""
    proportional = kp * value
    candidate_integral = integral + ki * value * dt_hours
    raw = proportional + candidate_integral

    saturated_high = raw > output_max
    saturated_low = raw < output_min

    if (saturated_high and value > 0) or (saturated_low and value < 0):
        candidate_integral = integral
        raw = proportional + candidate_integral

    clamped = max(output_min, min(output_max, raw))
    return clamped, candidate_integral, saturated_high, saturated_low


def apply_rate_limit(
    desired: float, last: float | None, max_delta: float
) -> Tuple[float, bool]:
    """Apply a symmetric rate limit between successive outputs."""
    if last is None:
        return desired, False
    delta = desired - last
    if abs(delta) <= max_delta:
        return desired, False
    limited = last + max_delta * (1 if delta > 0 else -1)
    return limited, True
