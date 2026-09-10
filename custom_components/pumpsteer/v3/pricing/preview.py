"""Deterministic, authority-free price classification for V3 shadow mode."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .policy import normalize_saving_level, price_policy_for_saving_level

MIN_CLASSIFICATION_POINTS = 4


class PriceBand(StrEnum):
    """Relative price band without any implied control action."""

    UNKNOWN = "unknown"
    CHEAP = "cheap"
    NORMAL = "normal"
    EXPENSIVE = "expensive"


class PricePreviewStatus(StrEnum):
    """Outcome of one shadow-only classification attempt."""

    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    UNINFORMATIVE = "uninformative"
    CLASSIFIED = "classified"


class PricePreviewReason(StrEnum):
    """Stable explanations intended for diagnostics and tests."""

    SAVING_LEVEL_ZERO = "saving_level_zero"
    PRICE_TIMELINE_MISSING = "price_timeline_missing"
    TOO_FEW_PRICE_POINTS = "too_few_price_points"
    PRICE_TIMELINE_GAP = "price_timeline_gap"
    CURRENT_PRICE_MISSING = "current_price_missing"
    PRICE_THRESHOLDS_NOT_SEPARATED = "price_thresholds_not_separated"
    PRICE_CLASSIFIED = "price_classified"


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value


def _finite_price(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as err:
        raise TypeError(f"{field_name} must be numeric") from err
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    return numeric


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One exact price interval in UTC; negative market prices are valid."""

    starts_at: datetime
    ends_at: datetime
    price_per_kwh: float
    source: str
    currency: str = "SEK"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "starts_at", _utc_datetime(self.starts_at, "starts_at")
        )
        object.__setattr__(self, "ends_at", _utc_datetime(self.ends_at, "ends_at"))
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        object.__setattr__(
            self,
            "price_per_kwh",
            _finite_price(self.price_per_kwh, "price_per_kwh"),
        )
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        if self.currency != "SEK":
            raise ValueError("currency must be SEK")

    def contains(self, instant: datetime) -> bool:
        """Use start-inclusive and end-exclusive interval semantics."""
        instant = _utc_datetime(instant, "instant")
        return self.starts_at <= instant < self.ends_at


@dataclass(frozen=True, slots=True)
class PriceTimeline:
    """Prices for one explicit comparison period in UTC."""

    points: tuple[PricePoint, ...]
    comparison_starts_at: datetime
    comparison_ends_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "comparison_starts_at",
            _utc_datetime(self.comparison_starts_at, "comparison_starts_at"),
        )
        object.__setattr__(
            self,
            "comparison_ends_at",
            _utc_datetime(self.comparison_ends_at, "comparison_ends_at"),
        )
        if self.comparison_ends_at <= self.comparison_starts_at:
            raise ValueError("comparison period must have positive duration")
        points = tuple(self.points)
        for index, point in enumerate(points):
            if not isinstance(point, PricePoint):
                raise TypeError(f"points[{index}] must be a PricePoint")
        expected_source = points[0].source if points else None
        expected_duration = points[0].ends_at - points[0].starts_at if points else None
        for index, point in enumerate(points):
            if (
                point.starts_at < self.comparison_starts_at
                or point.ends_at > self.comparison_ends_at
            ):
                raise ValueError("price points must stay inside the comparison period")
            if index == 0:
                continue
            previous = points[index - 1]
            if point.source != expected_source:
                raise ValueError("price points must use one source")
            if point.ends_at - point.starts_at != expected_duration:
                raise ValueError("price points must use one interval duration")
            if point.starts_at < previous.starts_at:
                raise ValueError("price points must be sorted by starts_at")
            if point.starts_at < previous.ends_at:
                raise ValueError("price points must not overlap")
        object.__setattr__(self, "points", points)

    @property
    def interval_duration(self) -> timedelta | None:
        """Return the uniform market interval, or None for an empty timeline."""
        if not self.points:
            return None
        return self.points[0].ends_at - self.points[0].starts_at

    @property
    def is_contiguous(self) -> bool:
        """Return whether adjacent intervals meet without missing time."""
        return all(
            previous.ends_at == current.starts_at
            for previous, current in zip(self.points, self.points[1:], strict=False)
        )

    @property
    def is_complete(self) -> bool:
        """Return whether points cover the exact comparison period without gaps."""
        return bool(self.points) and (
            self.points[0].starts_at == self.comparison_starts_at
            and self.points[-1].ends_at == self.comparison_ends_at
            and self.is_contiguous
        )

    def point_at(self, instant: datetime) -> PricePoint | None:
        """Return the point covering an instant, if the timeline contains it."""
        instant = _utc_datetime(instant, "instant")
        return next((point for point in self.points if point.contains(instant)), None)


@dataclass(frozen=True, slots=True)
class PriceThresholds:
    """Exact thresholds calculated by the documented nearest-rank method."""

    cheap_price: float
    expensive_price: float
    cheap_percentile: int
    expensive_percentile: int
    sample_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "cheap_price", _finite_price(self.cheap_price, "cheap_price")
        )
        object.__setattr__(
            self,
            "expensive_price",
            _finite_price(self.expensive_price, "expensive_price"),
        )
        for name in ("cheap_percentile", "expensive_percentile"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if not 0 <= self.cheap_percentile < self.expensive_percentile <= 100:
            raise ValueError("percentiles must be ordered between 0 and 100")
        if self.cheap_price > self.expensive_price:
            raise ValueError("cheap_price cannot exceed expensive_price")
        if isinstance(self.sample_count, bool) or not isinstance(
            self.sample_count, int
        ):
            raise TypeError("sample_count must be an integer")
        if self.sample_count < 1:
            raise ValueError("sample_count must be positive")


@dataclass(frozen=True, slots=True)
class ShadowPricePlan:
    """Explainable price preview that can never authorize heating control."""

    evaluated_at: datetime
    saving_level: int
    status: PricePreviewStatus
    reason: PricePreviewReason
    current_band: PriceBand = PriceBand.UNKNOWN
    current_price: float | None = None
    thresholds: PriceThresholds | None = None
    point_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evaluated_at", _utc_datetime(self.evaluated_at, "evaluated_at")
        )
        object.__setattr__(
            self, "saving_level", normalize_saving_level(self.saving_level)
        )
        object.__setattr__(self, "status", PricePreviewStatus(self.status))
        object.__setattr__(self, "reason", PricePreviewReason(self.reason))
        object.__setattr__(self, "current_band", PriceBand(self.current_band))
        if self.current_price is not None:
            object.__setattr__(
                self,
                "current_price",
                _finite_price(self.current_price, "current_price"),
            )
        if self.thresholds is not None and not isinstance(
            self.thresholds, PriceThresholds
        ):
            raise TypeError("thresholds must be PriceThresholds or None")
        if isinstance(self.point_count, bool) or not isinstance(self.point_count, int):
            raise TypeError("point_count must be an integer")
        if self.point_count < 0:
            raise ValueError("point_count must be non-negative")
        if self.thresholds is not None and (
            self.thresholds.sample_count != self.point_count
        ):
            raise ValueError("threshold sample_count must match point_count")
        if self.thresholds is not None:
            policy = price_policy_for_saving_level(self.saving_level)
            if (
                self.thresholds.cheap_percentile != policy.cheap_percentile
                or self.thresholds.expensive_percentile != policy.expensive_percentile
            ):
                raise ValueError("threshold percentiles must match saving level")
        self._validate_status_contract()

    def _validate_status_contract(self) -> None:
        """Reject contradictory public result combinations."""
        if self.status is PricePreviewStatus.DISABLED:
            if (
                self.saving_level != 0
                or self.reason is not PricePreviewReason.SAVING_LEVEL_ZERO
            ):
                raise ValueError("disabled status requires saving level zero")
            if self.current_band is not PriceBand.UNKNOWN:
                raise ValueError("disabled status requires unknown band")
            if self.current_price is not None or self.thresholds is not None:
                raise ValueError("disabled status cannot contain price details")
            return
        if self.saving_level == 0:
            raise ValueError("saving level zero requires disabled status")
        if self.status is PricePreviewStatus.UNAVAILABLE:
            allowed = {
                PricePreviewReason.PRICE_TIMELINE_MISSING,
                PricePreviewReason.PRICE_TIMELINE_GAP,
                PricePreviewReason.CURRENT_PRICE_MISSING,
            }
            if self.reason not in allowed:
                raise ValueError("unavailable status has incompatible reason")
            if self.current_band is not PriceBand.UNKNOWN:
                raise ValueError("unavailable status requires unknown band")
            if self.current_price is not None or self.thresholds is not None:
                raise ValueError("unavailable status cannot contain price details")
            return
        if self.status is PricePreviewStatus.UNINFORMATIVE:
            if self.reason is PricePreviewReason.TOO_FEW_PRICE_POINTS:
                if self.current_band is not PriceBand.UNKNOWN:
                    raise ValueError("insufficient samples require unknown band")
                if self.current_price is not None or self.thresholds is not None:
                    raise ValueError(
                        "insufficient samples cannot contain price details"
                    )
                return
            if self.reason is PricePreviewReason.PRICE_THRESHOLDS_NOT_SEPARATED:
                if self.current_band is not PriceBand.NORMAL:
                    raise ValueError("unseparated thresholds require normal band")
                if self.current_price is None or self.thresholds is None:
                    raise ValueError("unseparated thresholds require price details")
                if self.thresholds.cheap_price != self.thresholds.expensive_price:
                    raise ValueError("unseparated thresholds must have equal prices")
                return
            raise ValueError("uninformative status has incompatible reason")
        if self.reason is not PricePreviewReason.PRICE_CLASSIFIED:
            raise ValueError("classified status requires classified reason")
        if self.current_band is PriceBand.UNKNOWN:
            raise ValueError("classified status requires a known band")
        if self.current_price is None or self.thresholds is None:
            raise ValueError("classified status requires price details")
        if self.point_count < MIN_CLASSIFICATION_POINTS:
            raise ValueError("classified status requires enough price points")
        if self.thresholds.cheap_price >= self.thresholds.expensive_price:
            raise ValueError("classified status requires separated thresholds")
        if self.current_price <= self.thresholds.cheap_price:
            expected_band = PriceBand.CHEAP
        elif self.current_price >= self.thresholds.expensive_price:
            expected_band = PriceBand.EXPENSIVE
        else:
            expected_band = PriceBand.NORMAL
        if self.current_band is not expected_band:
            raise ValueError("current band must match price thresholds")

    @property
    def may_control_heat_pump(self) -> bool:
        return False

    @property
    def may_request_preheat(self) -> bool:
        return False

    @property
    def may_request_curtailment(self) -> bool:
        return False


def _nearest_rank(values: tuple[float, ...], percentile: int) -> float:
    """Return a deterministic nearest-rank percentile (rank = ceil(p*n/100))."""
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered) / 100))
    return ordered[rank - 1]


def build_shadow_price_plan(
    *,
    timeline: PriceTimeline | None,
    saving_level: object,
    evaluated_at: datetime,
) -> ShadowPricePlan:
    """Classify current price without creating any physical control request."""
    instant = _utc_datetime(evaluated_at, "evaluated_at")
    level = normalize_saving_level(saving_level)
    policy = price_policy_for_saving_level(level)
    point_count = 0 if timeline is None else len(timeline.points)
    if not policy.classification_enabled:
        return ShadowPricePlan(
            instant,
            level,
            PricePreviewStatus.DISABLED,
            PricePreviewReason.SAVING_LEVEL_ZERO,
            point_count=point_count,
        )
    if timeline is None:
        return ShadowPricePlan(
            instant,
            level,
            PricePreviewStatus.UNAVAILABLE,
            PricePreviewReason.PRICE_TIMELINE_MISSING,
        )
    if point_count == 0:
        return ShadowPricePlan(
            instant,
            level,
            PricePreviewStatus.UNAVAILABLE,
            PricePreviewReason.PRICE_TIMELINE_MISSING,
        )
    current = timeline.point_at(instant)
    if current is None:
        within_comparison_period = (
            timeline.comparison_starts_at <= instant < timeline.comparison_ends_at
        )
        return ShadowPricePlan(
            instant,
            level,
            PricePreviewStatus.UNAVAILABLE,
            PricePreviewReason.PRICE_TIMELINE_GAP
            if within_comparison_period
            else PricePreviewReason.CURRENT_PRICE_MISSING,
            point_count=point_count,
        )
    if point_count < MIN_CLASSIFICATION_POINTS:
        return ShadowPricePlan(
            instant,
            level,
            PricePreviewStatus.UNINFORMATIVE,
            PricePreviewReason.TOO_FEW_PRICE_POINTS,
            point_count=point_count,
        )
    if not timeline.is_complete:
        return ShadowPricePlan(
            instant,
            level,
            PricePreviewStatus.UNAVAILABLE,
            PricePreviewReason.PRICE_TIMELINE_GAP,
            point_count=point_count,
        )
    prices = tuple(point.price_per_kwh for point in timeline.points)
    cheap_price = _nearest_rank(prices, policy.cheap_percentile)
    expensive_price = _nearest_rank(prices, policy.expensive_percentile)
    thresholds = PriceThresholds(
        cheap_price=cheap_price,
        expensive_price=expensive_price,
        cheap_percentile=policy.cheap_percentile,
        expensive_percentile=policy.expensive_percentile,
        sample_count=point_count,
    )
    if cheap_price >= expensive_price:
        return ShadowPricePlan(
            instant,
            level,
            PricePreviewStatus.UNINFORMATIVE,
            PricePreviewReason.PRICE_THRESHOLDS_NOT_SEPARATED,
            current_band=PriceBand.NORMAL,
            current_price=current.price_per_kwh,
            thresholds=thresholds,
            point_count=point_count,
        )
    if current.price_per_kwh <= cheap_price:
        band = PriceBand.CHEAP
    elif current.price_per_kwh >= expensive_price:
        band = PriceBand.EXPENSIVE
    else:
        band = PriceBand.NORMAL
    return ShadowPricePlan(
        instant,
        level,
        PricePreviewStatus.CLASSIFIED,
        PricePreviewReason.PRICE_CLASSIFIED,
        current_band=band,
        current_price=current.price_per_kwh,
        thresholds=thresholds,
        point_count=point_count,
    )
