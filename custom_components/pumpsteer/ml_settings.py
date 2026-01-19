from typing import Final
import logging

_LOGGER = logging.getLogger(__name__)

ML_MODULE_VERSION: Final[str] = "1.0.0"

ML_DATA_FILE_PATH: Final[str] = "/config/pumpsteer_ml_data.json"
ML_MAX_SAVED_SESSIONS: Final[int] = 100
ML_MAX_SESSION_UPDATES: Final[int] = 100
ML_TRIMMED_UPDATES: Final[int] = 50
ML_DATA_VERSION: Final[str] = "1.0"

ML_MIN_SESSIONS_FOR_ANALYSIS: Final[int] = 3
ML_MIN_SESSIONS_FOR_RECOMMENDATIONS: Final[int] = 5
ML_MIN_SESSIONS_FOR_AUTOTUNE: Final[int] = 5
ML_MIN_HEATING_SESSIONS: Final[int] = 3
ML_ANALYSIS_RECENT_SESSIONS: Final[int] = 10

ML_SUCCESS_DURATION_THRESHOLD: Final[float] = 90.0
ML_SUCCESS_TEMP_DIFF_THRESHOLD: Final[float] = 0.3
ML_FAILURE_DURATION_THRESHOLD: Final[float] = 180.0
ML_MIN_DATA_POINTS: Final[int] = 2

ML_LONG_DURATION_THRESHOLD: Final[float] = 150.0
ML_SHORT_DURATION_THRESHOLD: Final[float] = 20.0
ML_HIGH_INERTIA_THRESHOLD: Final[float] = 3.0
ML_LOW_INERTIA_THRESHOLD: Final[float] = 1.0
ML_HIGH_AGGRESSIVENESS_THRESHOLD: Final[int] = 4
ML_LOW_AGGRESSIVENESS_THRESHOLD: Final[int] = 2

ML_EXCELLENT_SUCCESS_RATE: Final[float] = 85.0
ML_POOR_SUCCESS_RATE: Final[float] = 60.0
ML_HIGH_SUCCESS_RATE_THRESHOLD: Final[float] = 70.0
ML_INERTIA_ADJUSTMENT_STEP: Final[float] = 0.5
ML_AGGRESSIVENESS_ADJUSTMENT_STEP: Final[int] = 1

ML_AUTOTUNE_MIN_DAYS_BETWEEN: Final[int] = 2
ML_DRIFT_HIGH_THRESHOLD: Final[float] = 0.3
ML_DRIFT_LOW_THRESHOLD: Final[float] = -0.3
ML_GAIN_ADJUSTMENT_STEP: Final[float] = 0.05
ML_MAX_INTEGRAL_GAIN: Final[float] = 1.0
ML_MIN_INTEGRAL_GAIN: Final[float] = 0.0

ML_INERTIA_MAX_VALUE: Final[float] = 5.0
ML_INERTIA_MIN_VALUE: Final[float] = 0.5

ML_WARMING_TREND_THRESHOLD: Final[float] = 0.8
ML_MIN_FORECAST_HOURS: Final[int] = 2

ML_LEARN_PATIENCE_SESSIONS: Final[int] = 10
ML_RECENT_SESSIONS_WINDOW: Final[int] = 10

ML_NOTIFICATION_PREFIX: Final[str] = "🤖 PumpSteer ML"
ML_AUTOTUNE_NOTIFICATION_ID: Final[str] = "pumpsteer_autotune"
ML_RECOMMENDATION_NOTIFICATION_ID: Final[str] = "pumpsteer_recommendation"

ML_AUTOTUNE_BOOLEAN_ENTITY: Final[str] = "input_boolean.autotune_inertia"
ML_HOUSE_INERTIA_ENTITY: Final[str] = "input_number.pumpsteer_house_inertia"
ML_INTEGRAL_GAIN_ENTITY: Final[str] = "input_number.pumpsteer_integral_gain"

ML_DEBUG_MODE: Final[bool] = False
ML_LOG_SESSION_DETAILS: Final[bool] = True


def validate_ml_settings() -> None:
    """Validate ML-specific settings for consistency and logical values"""
    errors = []

    # Validate session thresholds
    if ML_MIN_SESSIONS_FOR_ANALYSIS <= 0:
        errors.append("ML_MIN_SESSIONS_FOR_ANALYSIS must be positive")

    if ML_MIN_SESSIONS_FOR_RECOMMENDATIONS < ML_MIN_SESSIONS_FOR_ANALYSIS:
        errors.append(
            "ML_MIN_SESSIONS_FOR_RECOMMENDATIONS must be >= ML_MIN_SESSIONS_FOR_ANALYSIS"
        )

    if ML_MIN_SESSIONS_FOR_AUTOTUNE < ML_MIN_SESSIONS_FOR_RECOMMENDATIONS:
        errors.append(
            "ML_MIN_SESSIONS_FOR_AUTOTUNE must be >= ML_MIN_SESSIONS_FOR_RECOMMENDATIONS"
        )

    # Validate duration thresholds
    if not (
        ML_SHORT_DURATION_THRESHOLD
        < ML_SUCCESS_DURATION_THRESHOLD
        < ML_LONG_DURATION_THRESHOLD
        < ML_FAILURE_DURATION_THRESHOLD
    ):
        errors.append(
            "Duration thresholds must be in ascending order: short < success < long < failure"
        )

    # Validate success rate thresholds
    if not (
        0
        <= ML_POOR_SUCCESS_RATE
        <= ML_HIGH_SUCCESS_RATE_THRESHOLD
        <= ML_EXCELLENT_SUCCESS_RATE
        <= 100
    ):
        errors.append(
            "Success rate thresholds must be in ascending order between 0 and 100"
        )

    # Validate auto-tune settings
    if ML_MIN_INTEGRAL_GAIN >= ML_MAX_INTEGRAL_GAIN:
        errors.append("ML_MIN_INTEGRAL_GAIN must be less than ML_MAX_INTEGRAL_GAIN")

    if ML_INERTIA_MIN_VALUE >= ML_INERTIA_MAX_VALUE:
        errors.append("ML_INERTIA_MIN_VALUE must be less than ML_INERTIA_MAX_VALUE")

    # Validate adjustment steps
    if ML_GAIN_ADJUSTMENT_STEP <= 0:
        errors.append("ML_GAIN_ADJUSTMENT_STEP must be positive")

    if ML_INERTIA_ADJUSTMENT_STEP <= 0:
        errors.append("ML_INERTIA_ADJUSTMENT_STEP must be positive")

    # Validate aggressiveness thresholds
    if ML_LOW_AGGRESSIVENESS_THRESHOLD >= ML_HIGH_AGGRESSIVENESS_THRESHOLD:
        errors.append(
            "ML_LOW_AGGRESSIVENESS_THRESHOLD must be less than ML_HIGH_AGGRESSIVENESS_THRESHOLD"
        )

    # Validate file settings
    if ML_MAX_SESSION_UPDATES <= 0 or ML_TRIMMED_UPDATES <= 0:
        errors.append("Session update limits must be positive")

    if ML_TRIMMED_UPDATES >= ML_MAX_SESSION_UPDATES:
        errors.append("ML_TRIMMED_UPDATES must be less than ML_MAX_SESSION_UPDATES")

    # Validate time settings
    if ML_AUTOTUNE_MIN_DAYS_BETWEEN <= 0:
        errors.append("ML_AUTOTUNE_MIN_DAYS_BETWEEN must be positive")

    if errors:
        error_msg = f"ML Settings validation failed: {'; '.join(errors)}"
        _LOGGER.error(error_msg)
        raise ValueError(error_msg)


def get_ml_settings_info() -> dict:
    """Get information about current ML settings"""
    return {
        "version": ML_MODULE_VERSION,
        "data_file": ML_DATA_FILE_PATH,
        "min_sessions_for_analysis": ML_MIN_SESSIONS_FOR_ANALYSIS,
        "min_sessions_for_recommendations": ML_MIN_SESSIONS_FOR_RECOMMENDATIONS,
        "min_sessions_for_autotune": ML_MIN_SESSIONS_FOR_AUTOTUNE,
        "success_criteria": {
            "max_duration_minutes": ML_SUCCESS_DURATION_THRESHOLD,
            "min_temp_diff": ML_SUCCESS_TEMP_DIFF_THRESHOLD,
        },
        "auto_tune_enabled": True,
        "debug_mode": ML_DEBUG_MODE,
    }


_LOGGER.debug(
    "PumpSteer ML settings module loaded (version %s)", ML_MODULE_VERSION
)
