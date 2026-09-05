"""Set up the PumpSteer V3 Home Assistant integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INDOOR_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_TARGET_TEMPERATURE,
    DEFAULT_TARGET_TEMPERATURE,
    PLATFORMS,
    PumpSteerEntryData,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one PumpSteer V3 entry in mandatory shadow mode."""
    from .v3.control.engine import ControlEngine
    from .v3.ha.coordinator import (
        HomeAssistantStateProvider,
        PumpSteerDataUpdateCoordinator,
    )
    from .v3.ha.learning_coordinator import ObservationLearningCoordinator
    from .v3.ha.learning_runtime import (
        LearningRuntimeConfig,
        ObservationLearningRuntime,
    )
    from .v3.ha.learning_store import HomeAssistantLearningStore
    from .v3.ha.recorder import RecorderHistoryAdapter
    from .v3.ha.runtime import PumpSteerRuntime, RuntimeConfig

    target_temperature = entry.data.get(
        CONF_TARGET_TEMPERATURE,
        DEFAULT_TARGET_TEMPERATURE,
    )
    runtime = PumpSteerRuntime(
        config=RuntimeConfig(
            indoor_entity=entry.data[CONF_INDOOR_ENTITY],
            outdoor_entity=entry.data[CONF_OUTDOOR_ENTITY],
            target_temperature=target_temperature,
        ),
        states=HomeAssistantStateProvider(hass),
        engine=ControlEngine(),
    )
    coordinator = PumpSteerDataUpdateCoordinator(hass, runtime)
    learning_runtime = None
    learning_coordinator = None
    learning_started_at = datetime.now(UTC)
    learning_store = HomeAssistantLearningStore(hass, entry.entry_id)
    try:
        restored_checkpoint = await learning_store.async_load(
            expected_entry_id=entry.entry_id,
            expected_indoor_entity=entry.data[CONF_INDOOR_ENTITY],
            expected_outdoor_entity=entry.data[CONF_OUTDOOR_ENTITY],
            not_after=learning_started_at,
        )
        learning_runtime = ObservationLearningRuntime(
            config=LearningRuntimeConfig(
                indoor_entity=entry.data[CONF_INDOOR_ENTITY],
                outdoor_entity=entry.data[CONF_OUTDOOR_ENTITY],
            ),
            recorder=RecorderHistoryAdapter(hass),
            started_at=learning_started_at,
            target_temperature=target_temperature,
            entry_id=entry.entry_id,
            store=learning_store,
            restored_checkpoint=restored_checkpoint,
        )
        await learning_runtime.async_initialize()
        learning_coordinator = ObservationLearningCoordinator(hass, learning_runtime)
    except Exception:
        _LOGGER.exception(
            "Observation learning checkpoint is unavailable; learning remains disabled"
        )
        if learning_runtime is not None:
            learning_runtime.stop()
    entry.runtime_data = PumpSteerEntryData(
        runtime=runtime,
        coordinator=coordinator,
        learning_runtime=learning_runtime,
        learning_coordinator=learning_coordinator,
    )

    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(coordinator.async_start_source_tracking())
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if learning_coordinator is not None:
        try:
            learning_coordinator.start()
        except Exception:
            _LOGGER.exception("Unable to start observation-only learning")
            learning_coordinator.stop()
        else:
            entry.async_on_unload(learning_coordinator.stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload all V3 platforms and registered listeners."""
    data: PumpSteerEntryData | None = getattr(entry, "runtime_data", None)
    if data is not None and data.learning_coordinator is not None:
        await data.learning_coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Expose the config-entry migration hook expected by Home Assistant core."""
    from .config_flow import async_migrate_entry as migrate_entry

    return await migrate_entry(hass, entry)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)
