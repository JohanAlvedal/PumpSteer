"""Tests for the Home Assistant-independent PumpSteer V3 domain."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pumpsteer.v3 import (
    ComfortPolicy,
    ControlDecision,
    ControlState,
    LearningStage,
    ModelConfidence,
    Observation,
    ReasonCode,
    SafetyPolicy,
    SensorReading,
    Unit,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def reading(value: float, unit: Unit = Unit.CELSIUS) -> SensorReading:
    return SensorReading(value=value, observed_at=NOW, unit=unit, source="test")


def test_observation_uses_positive_comfort_error_when_house_is_too_cold() -> None:
    observation = Observation(
        captured_at=NOW,
        indoor=reading(20.0),
        outdoor=reading(-5.0),
    )

    assert observation.comfort_error(21.5) == pytest.approx(1.5)


def test_control_decision_enforces_sign_contract() -> None:
    decision = ControlDecision.create(
        decided_at=NOW,
        state=ControlState.COMFORT,
        outdoor_temperature=2.0,
        heating_request=4.0,
        curtailment=1.5,
        reason_codes=[ReasonCode.COMFORT_BELOW_TARGET],
    )

    assert decision.virtual_temperature == pytest.approx(-0.5)


def test_control_decision_rejects_inconsistent_virtual_temperature() -> None:
    with pytest.raises(ValueError, match="must equal"):
        ControlDecision(
            decided_at=NOW,
            state=ControlState.COMFORT,
            outdoor_temperature=2.0,
            heating_request=4.0,
            curtailment=1.5,
            virtual_temperature=9.0,
            reason_codes=(ReasonCode.COMFORT_BELOW_TARGET,),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_reading_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        reading(value)


def test_reading_requires_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SensorReading(20.0, datetime(2026, 1, 15, 12, 0), Unit.CELSIUS, "test")


def test_observation_rejects_wrong_units() -> None:
    with pytest.raises(ValueError, match="indoor must use"):
        Observation(
            captured_at=NOW,
            indoor=reading(1.0, Unit.SEK_PER_KWH),
            outdoor=reading(-5.0),
        )


def test_sensor_age_rejects_future_reading() -> None:
    future = SensorReading(20.0, NOW + timedelta(seconds=1), Unit.CELSIUS, "test")

    with pytest.raises(ValueError, match="cannot be later"):
        future.age_at(NOW)


def test_policy_invariants_are_validated() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        ComfortPolicy(
            target_temperature=21.0,
            minimum_temperature=22.0,
            maximum_temperature=23.0,
        )

    with pytest.raises(ValueError, match="must be below"):
        SafetyPolicy(
            minimum_virtual_temperature=30.0,
            maximum_virtual_temperature=30.0,
        )


def test_model_confidence_has_bounded_score_and_counts() -> None:
    confidence = ModelConfidence(
        stage=LearningStage.PROVISIONAL,
        score=0.75,
        accepted_samples=100,
        validation_events=4,
    )

    assert confidence.stage is LearningStage.PROVISIONAL

    with pytest.raises(ValueError, match="between 0 and 1"):
        ModelConfidence(score=1.1)
