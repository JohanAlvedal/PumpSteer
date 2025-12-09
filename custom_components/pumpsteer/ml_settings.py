# ml_settings.py - Machine Learning specific settings
# Separate configuration file for ML functionality

from typing import Final
import logging

_LOGGER = logging.getLogger(__name__)

# === ML VERSION INFO ===
ML_MODULE_VERSION: Final[str] = "1.0.0"

# === ML DATA COLLECTION ===
ML_DATA_FILE_PATH: Final[str] = "/config/pumpsteer_ml_data.json"
ML_MAX_SAVED_SESSIONS: Final[int] = 100  # Maximum sessions to keep in file
ML_MAX_SESSION_UPDATES: Final[int] = 100  # Maximum updates per session in memory
ML_TRIMMED_UPDATES: Final[int] = 50  # Trim to this many when max is reached
ML_DATA_VERSION: Final[str] = "1.0"  # Data format version

# === ML ANALYSIS THRESHOLDS ===
ML_MIN_SESSIONS_FOR_ANALYSIS: Final[int] = 3  # Minimum sessions needed for analysis
ML_MIN_SESSIONS_FOR_RECOMMENDATIONS: Final[int] = 5  # Minimum for recommendations
ML_MIN_SESSIONS_FOR_AUTOTUNE: Final[int] = 5  # Minimum for auto-tune
ML_MIN_HEATING_SESSIONS: Final[int] = 3  # Minimum heating sessions for analysis
ML_ANALYSIS_RECENT_SESSIONS: Final[int] = 10  # How many recent sessions to analyze

# === ML SUCCESS CRITERIA ===
ML_SUCCESS_DURATION_THRESHOLD: Final[float] = 90.0  # Minutes - under this = success
ML_SUCCESS_TEMP_DIFF_THRESHOLD: Final[float] = 0.3  # °C - minimum temp diff for success
ML_FAILURE_DURATION_THRESHOLD: Final[float] = 180.0  # Minutes - over this = failure
ML_MIN_DATA_POINTS: Final[int] = 2  # Minimum data points for trend analysis

# === ML PERFORMANCE ANALYSIS ===
ML_LONG_DURATION_THRESHOLD: Final[float] = 150.0  # Minutes - indicates slow house
ML_SHORT_DURATION_THRESHOLD: Final[float] = 20.0  # Minutes - indicates fast house
ML_HIGH_INERTIA_THRESHOLD: Final[float] = (
    3.0  # House inertia >= 3.0 indicates slow response
)
ML_LOW_INERTIA_THRESHOLD: Final[float] = (
    1.0  # House inertia <= 1.0 indicates fast response
)
ML_HIGH_AGGRESSIVENESS_THRESHOLD: Final[int] = 4  # Aggressiveness - high savings
ML_LOW_AGGRESSIVENESS_THRESHOLD: Final[int] = 2  # Aggressiveness - comfort focus

# === ML RECOMMENDATION THRESHOLDS ===
ML_EXCELLENT_SUCCESS_RATE: Final[float] = 85.0  # % - excellent performance
ML_POOR_SUCCESS_RATE: Final[float] = 60.0  # % - needs improvement
ML_HIGH_SUCCESS_RATE_THRESHOLD: Final[float] = 70.0  # % - aggressiveness too high
ML_INERTIA_ADJUSTMENT_STEP: Final[float] = 0.5  # Step size for inertia adjustments
ML_AGGRESSIVENESS_ADJUSTMENT_STEP: Final[int] = 1  # Step size for aggressiveness

# === ML AUTO-TUNE SETTINGS ===
ML_AUTOTUNE_MIN_DAYS_BETWEEN: Final[int] = 2  # Days between auto-tune adjustments
ML_DRIFT_HIGH_THRESHOLD: Final[float] = 0.3  # Temperature drift - increase gain
ML_DRIFT_LOW_THRESHOLD: Final[float] = -0.3  # Temperature drift - decrease gain
ML_GAIN_ADJUSTMENT_STEP: Final[float] = 0.05  # Step size for gain adjustments
ML_MAX_INTEGRAL_GAIN: Final[float] = 1.0  # Maximum integral gain value
ML_MIN_INTEGRAL_GAIN: Final[float] = 0.0  # Minimum integral gain value

# === ML HOUSE INERTIA AUTO-TUNE ===
ML_INERTIA_MAX_VALUE: Final[float] = 5.0  # Maximum house inertia value
ML_INERTIA_MIN_VALUE: Final[float] = 0.5  # Minimum house inertia value

# === ML TREND DETECTION ===
ML_WARMING_TREND_THRESHOLD: Final[float] = 0.8  # 80% of hours must be warmer
ML_MIN_FORECAST_HOURS: Final[int] = 2  # Minimum hours for meaningful analysis

# === ML SESSION LIMITS ===
ML_LEARN_PATIENCE_SESSIONS: Final[int] = 10  # Wait this many before major changes
ML_RECENT_SESSIONS_WINDOW: Final[int] = 10  # Window for recent performance analysis

# === ML NOTIFICATION SETTINGS ===
ML_NOTIFICATION_PREFIX: Final[str] = "🤖 PumpSteer ML"
ML_AUTOTUNE_NOTIFICATION_ID: Final[str] = "pumpsteer_autotune"
ML_RECOMMENDATION_NOTIFICATION_ID: Final[str] = "pumpsteer_recommendation"

# === ML HOME ASSISTANT ENTITY IDs ===
ML_AUTOTUNE_BOOLEAN_ENTITY: Final[str] = "input_boolean.autotune_inertia"
ML_HOUSE_INERTIA_ENTITY: Final[str] = "input_number.pumpsteer_house_inertia"
ML_INTEGRAL_GAIN_ENTITY: Final[str] = "input_number.pumpsteer_integral_gain"

# === ML LOGGING ===
ML_DEBUG_MODE: Final[bool] = False  # Enable detailed ML debug logging
ML_LOG_SESSION_DETAILS: Final[bool] = True  # Log detailed session information


def validate_ml_settings() -> None:
    """Validate ML-specific settings for consistency and logical values."""
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
    """Get information about current ML settings."""
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


# Run validation on import
try:
    validate_ml_settings()
    _LOGGER.debug(
        "PumpSteer ML settings loaded successfully (version %s)", ML_MODULE_VERSION
    )
except Exception as e:
    _LOGGER.error("Failed to load PumpSteer ML settings: %s", e)
    raise
