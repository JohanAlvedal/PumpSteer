"""Set up the PumpSteer V3 Home Assistant integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INDOOR_ENTITY,
    CONF_OHMON_MQTT_BASE_TOPIC,
    CONF_OHMON_WATCHDOG_CONFIRMED,
    CONF_OUTDOOR_ENTITY,
    CONF_OUTPUT_MODE,
    CONF_TARGET_TEMPERATURE,
    DEFAULT_TARGET_TEMPERATURE,
    OUTPUT_MODE_OHMON_MQTT,
    OUTPUT_MODE_SHADOW,
    PLATFORMS,
    PumpSteerEntryData,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one isolated PumpSteer V3 runtime and its selected output."""
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
    from .v3.ha.ohmon_output import (
        HomeAssistantMqttTransport,
        OhmonMqttConfig,
        OhmonMqttOutput,
    )
    from .v3.ha.recorder import RecorderHistoryAdapter
    from .v3.ha.runtime import PumpSteerRuntime, RuntimeConfig

    source_config = {**entry.data, **getattr(entry, "options", {})}
    indoor_entity = source_config[CONF_INDOOR_ENTITY]
    outdoor_entity = source_config[CONF_OUTDOOR_ENTITY]
    target_temperature = entry.data.get(
        CONF_TARGET_TEMPERATURE,
        DEFAULT_TARGET_TEMPERATURE,
    )
    output = None
    output_mode = source_config.get(CONF_OUTPUT_MODE, OUTPUT_MODE_SHADOW)
    if output_mode == OUTPUT_MODE_OHMON_MQTT:
        output = OhmonMqttOutput(
            config=OhmonMqttConfig(
                base_topic=source_config.get(CONF_OHMON_MQTT_BASE_TOPIC, ""),
                watchdog_confirmed=source_config.get(
                    CONF_OHMON_WATCHDOG_CONFIRMED, False
                ),
            ),
            transport=HomeAssistantMqttTransport(hass),
        )
        await output.async_initialize()
    runtime = PumpSteerRuntime(
        config=RuntimeConfig(
            indoor_entity=indoor_entity,
            outdoor_entity=outdoor_entity,
            target_temperature=target_temperature,
        ),
        states=HomeAssistantStateProvider(hass),
        engine=ControlEngine(),
        output=output,
    )
    coordinator = PumpSteerDataUpdateCoordinator(hass, runtime)
    learning_runtime = None
    learning_coordinator = None
    learning_started_at = datetime.now(UTC)
    learning_store = HomeAssistantLearningStore(hass, entry.entry_id)
    try:
        restored_checkpoint = await learning_store.async_load(
            expected_entry_id=entry.entry_id,
            expected_indoor_entity=indoor_entity,
            expected_outdoor_entity=outdoor_entity,
            not_after=learning_started_at,
        )
        learning_runtime = ObservationLearningRuntime(
            config=LearningRuntimeConfig(
                indoor_entity=indoor_entity,
                outdoor_entity=outdoor_entity,
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

    try:
        await coordinator.async_config_entry_first_refresh()
        entry.async_on_unload(coordinator.async_start_source_tracking())
        entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        try:
            await runtime.async_shutdown()
        except Exception:
            _LOGGER.exception(
                "Unable to request physical-output bypass after setup failure"
            )
        if learning_runtime is not None:
            learning_runtime.stop()
        raise
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
    if data is not None:
        try:
            await data.runtime.async_shutdown()
        except Exception:
            _LOGGER.exception("Unable to request physical-output bypass during unload")
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
