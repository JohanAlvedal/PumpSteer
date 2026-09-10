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
INTEGRATION_VERSION = "3.0.0-alpha.5"
PLATFORMS = ("climate", "number", "sensor")

CONF_INDOOR_ENTITY = "indoor_temp_entity"
CONF_OUTDOOR_ENTITY = "outdoor_temp_entity"
CONF_TARGET_TEMPERATURE = "target_temperature"
CONF_SAVING_LEVEL = "saving_level"
CONF_OUTPUT_MODE = "output_mode"
CONF_OHMON_MQTT_BASE_TOPIC = "ohmon_mqtt_base_topic"
CONF_OHMON_WATCHDOG_CONFIRMED = "ohmon_watchdog_confirmed"

OUTPUT_MODE_SHADOW = "shadow"
OUTPUT_MODE_OHMON_MQTT = "ohmon_mqtt"

DEFAULT_TARGET_TEMPERATURE = 21.0
MIN_TARGET_TEMPERATURE = 5.0
MAX_TARGET_TEMPERATURE = 35.0


@dataclass(slots=True)
class PumpSteerEntryData:
    """Runtime objects owned by one V3 config entry."""

    runtime: PumpSteerRuntime
    coordinator: PumpSteerDataUpdateCoordinator
    learning_runtime: ObservationLearningRuntime | None = None
    learning_coordinator: ObservationLearningCoordinator | None = None
