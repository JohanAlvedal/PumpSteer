"""Constants and entry runtime types for PumpSteer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .v3.ha.coordinator import PumpSteerDataUpdateCoordinator
    from .v3.ha.runtime import PumpSteerRuntime

DOMAIN = "pumpsteer"
PLATFORMS = ("climate",)

CONF_INDOOR_ENTITY = "indoor_temp_entity"
CONF_OUTDOOR_ENTITY = "outdoor_temp_entity"
CONF_TARGET_TEMPERATURE = "target_temperature"

DEFAULT_TARGET_TEMPERATURE = 21.0
MIN_TARGET_TEMPERATURE = 5.0
MAX_TARGET_TEMPERATURE = 35.0


@dataclass(slots=True)
class PumpSteerEntryData:
    """Runtime objects owned by one V3 config entry."""

    runtime: PumpSteerRuntime
    coordinator: PumpSteerDataUpdateCoordinator
