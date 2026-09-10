"""Automatic, comfort-bounded preheat planning for PumpSteer V3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from ..models import ComfortPolicy, Observation
from ..pricing import PriceBand, normalize_saving_level
from ..validation import finite_float


class PreheatReason(StrEnum):
    """Stable explanations for one automatic preheat evaluation."""

    SAVING_DISABLED = "saving_disabled"
    NO_PRICE_OPPORTUNITY = "no_price_opportunity"
    PRICE_NOT_CHEAP = "price_not_cheap"
    OUTSIDE_LOOKAHEAD = "outside_lookahead"
    PREDICTION_UNAVAILABLE = "prediction_unavailable"
    PREDICTION_NOT_AUTHORIZED = "prediction_not_authorized"
    NO_PREDICTED_COMFORT_RISK = "no_predicted_comfort_risk"
    HOUSE_ALREADY_WARM = "house_already_warm"
    NO_COMFORT_HEADROOM = "no_comfort_headroom"
    PREHEAT_REQUIRED = "preheat_required"


@dataclass(frozen=True, slots=True)
class PreheatContext:
    """Validated future context supplied by price and thermal planning adapters."""

    current_price_band: PriceBand
    time_until_expensive: timedelta | None = None
    expensive_duration: timedelta | None = None
    predicted_min_indoor_temperature: float | None = None
    prediction_authorized: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "current_price_band", PriceBand(self.current_price_band)
        )
        for name in ("time_until_expensive", "expensive_duration"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, timedelta):
                    raise TypeError(f"{name} must be a timedelta or None")
                if value <= timedelta(0):
                    raise ValueError(f"{name} must be positive when present")
        if self.predicted_min_indoor_temperature is not None:
            object.__setattr__(
                self,
                "predicted_min_indoor_temperature",
                finite_float(
                    self.predicted_min_indoor_temperature,
                    "predicted_min_indoor_temperature",
                ),
            )
        if not isinstance(self.prediction_authorized, bool):
            raise TypeError("prediction_authorized must be a boolean")


@dataclass(frozen=True, slots=True)
class AutomaticPreheatPolicy:
    """Product-owned limits for automatic preheat behaviour."""

    lookahead: timedelta = timedelta(hours=6)
    comfort_reserve_c: float = 0.2
    maximum_target_lift_c: float = 0.8
    maximum_start_above_target_c: float = 0.75
    minimum_target_above_indoor_c: float = 0.2

    def __post_init__(self) -> None:
        if not isinstance(self.lookahead, timedelta):
            raise TypeError("lookahead must be a timedelta")
        if self.lookahead <= timedelta(0):
            raise ValueError("lookahead must be positive")
        for name in (
            "comfort_reserve_c",
            "maximum_target_lift_c",
            "maximum_start_above_target_c",
            "minimum_target_above_indoor_c",
        ):
            value = finite_float(getattr(self, name), name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class PreheatPlan:
    """Explainable preheat proposal expressed as a temporary comfort target."""

    active: bool
    reason: PreheatReason
    effective_target_temperature: float
    target_lift_c: float = 0.0
    predicted_min_indoor_temperature: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.active, bool):
            raise TypeError("active must be a boolean")
        object.__setattr__(self, "reason", PreheatReason(self.reason))
        object.__setattr__(
            self,
            "effective_target_temperature",
            finite_float(
                self.effective_target_temperature,
                "effective_target_temperature",
            ),
        )
        lift = finite_float(self.target_lift_c, "target_lift_c")
        if lift < 0:
            raise ValueError("target_lift_c must be non-negative")
        object.__setattr__(self, "target_lift_c", lift)
        if self.predicted_min_indoor_temperature is not None:
            object.__setattr__(
                self,
                "predicted_min_indoor_temperature",
                finite_float(
                    self.predicted_min_indoor_temperature,
                    "predicted_min_indoor_temperature",
                ),
            )
        if self.active and self.reason is not PreheatReason.PREHEAT_REQUIRED:
            raise ValueError("active preheat requires PREHEAT_REQUIRED reason")
        if not self.active and self.target_lift_c != 0.0:
            raise ValueError("inactive preheat cannot contain a target lift")


def plan_automatic_preheat(
    *,
    observation: Observation,
    comfort_policy: ComfortPolicy,
    saving_level: object,
    context: PreheatContext | None,
    policy: AutomaticPreheatPolicy | None = None,
) -> PreheatPlan:
    """Plan preheat only for a real future cost shift and predicted comfort need.

    Cheap electricity alone never authorizes extra heating. The planner also refuses
    to act without a separately authorized indoor-temperature prediction. Weather is
    therefore useful input to prediction, but is not itself a mandatory capability.
    """
    if not isinstance(observation, Observation):
        raise TypeError("observation must be an Observation")
    if not isinstance(comfort_policy, ComfortPolicy):
        raise TypeError("comfort_policy must be a ComfortPolicy")
    if context is not None and not isinstance(context, PreheatContext):
        raise TypeError("context must be a PreheatContext or None")
    level = normalize_saving_level(saving_level)
    limits = policy or AutomaticPreheatPolicy()

    def inactive(reason: PreheatReason) -> PreheatPlan:
        return PreheatPlan(
            active=False,
            reason=reason,
            effective_target_temperature=comfort_policy.target_temperature,
            predicted_min_indoor_temperature=(
                context.predicted_min_indoor_temperature
                if context is not None
                else None
            ),
        )

    if level == 0:
        return inactive(PreheatReason.SAVING_DISABLED)
    if context is None:
        return inactive(PreheatReason.NO_PRICE_OPPORTUNITY)
    if context.time_until_expensive is None or context.expensive_duration is None:
        return inactive(PreheatReason.NO_PRICE_OPPORTUNITY)
    if context.current_price_band is not PriceBand.CHEAP:
        return inactive(PreheatReason.PRICE_NOT_CHEAP)
    if context.time_until_expensive > limits.lookahead:
        return inactive(PreheatReason.OUTSIDE_LOOKAHEAD)
    if context.predicted_min_indoor_temperature is None:
        return inactive(PreheatReason.PREDICTION_UNAVAILABLE)
    if not context.prediction_authorized:
        return inactive(PreheatReason.PREDICTION_NOT_AUTHORIZED)

    predicted_min = context.predicted_min_indoor_temperature
    predicted_risk = comfort_policy.target_temperature - predicted_min
    if predicted_risk <= 0.0:
        return inactive(PreheatReason.NO_PREDICTED_COMFORT_RISK)

    indoor = observation.indoor.value
    if indoor - comfort_policy.target_temperature > limits.maximum_start_above_target_c:
        return inactive(PreheatReason.HOUSE_ALREADY_WARM)

    comfort_headroom = comfort_policy.maximum_temperature - indoor
    if comfort_headroom <= 0.0:
        return inactive(PreheatReason.NO_COMFORT_HEADROOM)

    requested_lift = min(
        limits.maximum_target_lift_c,
        predicted_risk + limits.comfort_reserve_c,
    )
    maximum_preheat_target = min(
        comfort_policy.maximum_temperature,
        comfort_policy.target_temperature + limits.maximum_target_lift_c,
    )
    desired_target = max(
        comfort_policy.target_temperature + requested_lift,
        indoor + limits.minimum_target_above_indoor_c,
    )
    effective_target = min(maximum_preheat_target, desired_target)
    if effective_target <= indoor:
        return inactive(PreheatReason.NO_COMFORT_HEADROOM)

    return PreheatPlan(
        active=True,
        reason=PreheatReason.PREHEAT_REQUIRED,
        effective_target_temperature=effective_target,
        target_lift_c=max(0.0, effective_target - comfort_policy.target_temperature),
        predicted_min_indoor_temperature=predicted_min,
    )
