"""Stable enumerations used by the PumpSteer V3 domain."""

from __future__ import annotations

from enum import StrEnum


class Unit(StrEnum):
    """Units accepted at the domain boundary."""

    CELSIUS = "°C"
    SEK_PER_KWH = "SEK/kWh"


class LearningStage(StrEnum):
    """Authority granted to the learned thermal model."""

    UNINITIALIZED = "uninitialized"
    OBSERVING = "observing"
    PROVISIONAL = "provisional"
    VALIDATED = "validated"
    DEGRADED = "degraded"
    STALE = "stale"


class ControlState(StrEnum):
    """Mutually exclusive high-level controller states."""

    OFF = "off"
    SHADOW = "shadow"
    PASSTHROUGH = "passthrough"
    COMFORT = "comfort"
    PREHEAT = "preheat"
    CURTAIL = "curtail"
    RECOVERY = "recovery"
    SUMMER_PASSTHROUGH = "summer_passthrough"
    DEGRADED = "degraded"
    FAILSAFE = "failsafe"


class ReasonCode(StrEnum):
    """Stable, machine-readable explanations for control decisions."""

    COMFORT_BELOW_TARGET = "comfort_below_target"
    COMFORT_WITHIN_BAND = "comfort_within_band"
    PREDICTED_COMFORT_RISK = "predicted_comfort_risk"
    PRICE_SHIFT_BENEFICIAL = "price_shift_beneficial"
    MODEL_AUTHORITY_INSUFFICIENT = "model_authority_insufficient"
    OPTIONAL_FORECAST_MISSING = "optional_forecast_missing"
    CRITICAL_SENSOR_INVALID = "critical_sensor_invalid"
    CRITICAL_SENSOR_STALE = "critical_sensor_stale"
    SENSOR_TIME_REGRESSION = "sensor_time_regression"
    OUTPUT_RATE_LIMITED = "output_rate_limited"
    OUTPUT_SATURATED = "output_saturated"
    MODEL_OUTSIDE_VALID_DOMAIN = "model_outside_valid_domain"
    INTERNAL_FAILSAFE = "internal_failsafe"
    SUMMER_PASSTHROUGH = "summer_passthrough"
    USER_DISABLED = "user_disabled"
    SHADOW_MODE = "shadow_mode"
    PRICE_UNAVAILABLE = "price_unavailable"
    FORECAST_UNAVAILABLE = "forecast_unavailable"
    INDOOR_SENSOR_INVALID = "indoor_sensor_invalid"
    OUTDOOR_SENSOR_INVALID = "outdoor_sensor_invalid"
    STALE_SENSOR = "stale_sensor"
    OUTPUT_UNAVAILABLE = "output_unavailable"
    SAFETY_CLAMP = "safety_clamp"
