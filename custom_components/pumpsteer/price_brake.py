from dataclasses import dataclass
import math
from statistics import median
from typing import List, Optional


@dataclass
class PriceBlock:
    """Represents a contiguous expensive price block."""

    start_index: int
    end_index: int
    dt_minutes: int
    area: float
    peak: float

    @property
    def duration_minutes(self) -> int:
        """Return the block duration in minutes."""
        return (self.end_index - self.start_index + 1) * self.dt_minutes

    @property
    def start_offset_minutes(self) -> int:
        """Return the start offset relative to now in minutes."""
        return self.start_index * self.dt_minutes

    @property
    def end_offset_minutes(self) -> int:
        """Return the end offset relative to now in minutes."""
        return (self.end_index + 1) * self.dt_minutes


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp a value between min and max."""
    return max(min_value, min(max_value, value))


def smoothstep(t: float) -> float:
    """Smoothstep interpolation for t in [0, 1]."""
    t_clamped = clamp(t, 0.0, 1.0)
    return t_clamped * t_clamped * (3.0 - 2.0 * t_clamped)


def compute_percentile(values: List[float], percentile: float) -> float:
    """Compute a percentile using linear interpolation."""
    if not values:
        return 0.0
    if percentile <= 0:
        return min(values)
    if percentile >= 100:
        return max(values)
    sorted_values = sorted(values)
    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(sorted_values[int(rank)])
    weight = rank - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def build_forward_price_series(
    prices: List[float],
    start_index: int,
    dt_minutes: int,
    max_hours: int = 24,
) -> List[float]:
    """Build a forward price series from now for a limited horizon."""
    if not prices:
        return []
    safe_start = max(0, min(start_index, len(prices) - 1))
    max_steps = max(1, int(round(max_hours * 60 / dt_minutes)))
    return prices[safe_start : safe_start + max_steps]


def compute_baseline(prices: List[float]) -> float:
    """Compute baseline using the median of the provided prices."""
    if not prices:
        return 0.0
    return float(median(prices))


def compute_threshold(
    prices: List[float],
    baseline: float,
    threshold_delta: float,
    threshold_percentile: Optional[float],
) -> float:
    """Compute the expensive threshold from baseline or percentile."""
    if threshold_percentile is not None:
        return compute_percentile(prices, threshold_percentile)
    return baseline + threshold_delta


def compute_block_area(
    prices: List[float],
    start_index: int,
    end_index: int,
    threshold: float,
    dt_minutes: int,
) -> PriceBlock:
    """Compute area and peak for a block and return a PriceBlock."""
    dt_hours = dt_minutes / 60.0
    area = 0.0
    peak = threshold
    for price in prices[start_index : end_index + 1]:
        area += max(price - threshold, 0.0) * dt_hours
        peak = max(peak, price)
    return PriceBlock(
        start_index=start_index,
        end_index=end_index,
        dt_minutes=dt_minutes,
        area=area,
        peak=peak,
    )


def detect_expensive_blocks(
    prices: List[float],
    threshold: float,
    dt_minutes: int,
    min_block_duration_min: int,
) -> List[PriceBlock]:
    """Detect contiguous expensive blocks above a threshold."""
    blocks: List[PriceBlock] = []
    if not prices:
        return blocks
    in_block = False
    block_start = 0
    for index, price in enumerate(prices):
        if price > threshold:
            if not in_block:
                in_block = True
                block_start = index
        elif in_block:
            block = compute_block_area(
                prices, block_start, index - 1, threshold, dt_minutes
            )
            if block.duration_minutes >= min_block_duration_min:
                blocks.append(block)
            in_block = False
    if in_block:
        block = compute_block_area(
            prices, block_start, len(prices) - 1, threshold, dt_minutes
        )
        if block.duration_minutes >= min_block_duration_min:
            blocks.append(block)
    return blocks


def select_price_block(blocks: List[PriceBlock]) -> Optional[PriceBlock]:
    """Select the most relevant block by area, then by earliest start."""
    if not blocks:
        return None
    return max(blocks, key=lambda block: (block.area, -block.start_index))


def compute_brake_level(
    block: Optional[PriceBlock],
    amplitude: float,
    pre_brake_minutes: int,
    post_release_minutes: int,
    now_offset_minutes: float,
) -> float:
    """Compute a smooth brake level around a block."""
    if block is None or amplitude <= 0:
        return 0.0

    start = block.start_offset_minutes
    end = block.end_offset_minutes

    pre_start = start - pre_brake_minutes
    post_end = end + post_release_minutes

    if now_offset_minutes < pre_start:
        return 0.0
    if pre_brake_minutes > 0 and pre_start <= now_offset_minutes < start:
        progress = (now_offset_minutes - pre_start) / pre_brake_minutes
        return amplitude * smoothstep(progress)
    if start <= now_offset_minutes < end:
        return amplitude
    if post_release_minutes > 0 and end <= now_offset_minutes < post_end:
        progress = (now_offset_minutes - end) / post_release_minutes
        return amplitude * (1.0 - smoothstep(progress))
    return 0.0


def compute_price_brake(
    forward_prices: List[float],
    dt_minutes: int,
    threshold_delta: float,
    threshold_percentile: Optional[float],
    min_block_duration_min: int,
    pre_brake_minutes: int,
    post_release_minutes: int,
    area_scale: float,
    now_offset_minutes: float,
) -> dict:
    """Compute price brake metadata and raw brake level."""
    if not forward_prices:
        return {
            "baseline": 0.0,
            "threshold": 0.0,
            "area": 0.0,
            "amplitude": 0.0,
            "brake_level": 0.0,
            "block": None,
        }

    baseline = compute_baseline(forward_prices)
    threshold = compute_threshold(
        forward_prices, baseline, threshold_delta, threshold_percentile
    )
    blocks = detect_expensive_blocks(
        forward_prices, threshold, dt_minutes, min_block_duration_min
    )
    block = select_price_block(blocks)
    area = block.area if block else 0.0
    safe_area_scale = area_scale if area_scale > 0 else 1.0
    amplitude = clamp(area / safe_area_scale, 0.0, 1.0) if block else 0.0
    brake_level = compute_brake_level(
        block,
        amplitude,
        pre_brake_minutes,
        post_release_minutes,
        now_offset_minutes,
    )

    return {
        "baseline": baseline,
        "threshold": threshold,
        "area": area,
        "amplitude": amplitude,
        "brake_level": brake_level,
        "block": block,
    }
