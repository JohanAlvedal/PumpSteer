"""Constants and entry runtime types for PumpSteer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .v3.ha.coordinator import PumpSteerDataUpdateCoordinator
    from .v3.ha.learning_coordinator import ObservationLearningCoordinator
    from .v3.ha.learning_runtime import ObservationLearningRuntime
    from .v3.ha.runtime import PumpSteerRuntime

DOMAIN = "pumpsteer"
INTEGRATION_VERSION = "3.0.0-alpha.7"
PLATFORMS = ("climate", "number", "sensor")

CONF_INDOOR_ENTITY = "indoor_temp_entity"
CONF_OUTDOOR_ENTITY = "outdoor_temp_entity"
CONF_TARGET_TEMPERATURE = "target_temperature"
CONF_SAVING_LEVEL = "saving_level"
CONF_COMFORT_MINIMUM_TEMPERATURE = "comfort_minimum_temperature"
CONF_COMFORT_MAXIMUM_TEMPERATURE = "comfort_maximum_temperature"
CONF_SUMMER_THRESHOLD = "summer_threshold"
CONF_SUMMER_HYSTERESIS = "summer_hysteresis"
CONF_MAXIMUM_SENSOR_AGE_MINUTES = "maximum_sensor_age_minutes"
CONF_RECOVERY_VALID_OBSERVATIONS = "recovery_valid_observations"
CONF_OUTPUT_MODE = "output_mode"
CONF_OHMON_MQTT_BASE_TOPIC = "ohmon_mqtt_base_topic"
CONF_OHMON_WATCHDOG_CONFIRMED = "ohmon_watchdog_confirmed"
CONF_GOS_COMMAND_SERVICE = "gos_command_service"
CONF_GOS_COMMAND_PAYLOAD_TEMPLATE = "gos_command_payload_template"
CONF_GOS_SAFE_SERVICE = "gos_safe_service"
CONF_GOS_SAFE_PAYLOAD_TEMPLATE = "gos_safe_payload_template"
CONF_GOS_SAFE_ACTION_CONFIRMED = "gos_safe_action_confirmed"

OUTPUT_MODE_SHADOW = "shadow"
OUTPUT_MODE_OHMON_MQTT = "ohmon_mqtt"
OUTPUT_MODE_GENERIC = "generic_output"

DEFAULT_TARGET_TEMPERATURE = 21.0
DEFAULT_COMFORT_MINIMUM_TEMPERATURE = 19.5
DEFAULT_COMFORT_MAXIMUM_TEMPERATURE = 23.0
DEFAULT_SUMMER_THRESHOLD = 18.0
DEFAULT_SUMMER_HYSTERESIS = 1.0
DEFAULT_MAXIMUM_SENSOR_AGE_MINUTES = 10
DEFAULT_RECOVERY_VALID_OBSERVATIONS = 3
MIN_TARGET_TEMPERATURE = 5.0
MAX_TARGET_TEMPERATURE = 35.0


@dataclass(slots=True)
class PumpSteerEntryData:
    """Runtime objects owned by one V3 config entry."""

    runtime: PumpSteerRuntime
    coordinator: PumpSteerDataUpdateCoordinator
    learning_runtime: ObservationLearningRuntime | None = None
    learning_coordinator: ObservationLearningCoordinator | None = None
