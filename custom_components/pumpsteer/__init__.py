"""Set up the PumpSteer V3 Home Assistant integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_COMFORT_MAXIMUM_TEMPERATURE,
    CONF_COMFORT_MINIMUM_TEMPERATURE,
    CONF_GOS_COMMAND_PAYLOAD_TEMPLATE,
    CONF_GOS_COMMAND_SERVICE,
    CONF_GOS_SAFE_ACTION_CONFIRMED,
    CONF_GOS_SAFE_PAYLOAD_TEMPLATE,
    CONF_GOS_SAFE_SERVICE,
    CONF_INDOOR_ENTITY,
    CONF_MAXIMUM_SENSOR_AGE_MINUTES,
    CONF_OHMON_MQTT_BASE_TOPIC,
    CONF_OHMON_WATCHDOG_CONFIRMED,
    CONF_OUTDOOR_ENTITY,
    CONF_OUTPUT_MODE,
    CONF_RECOVERY_VALID_OBSERVATIONS,
    CONF_SUMMER_HYSTERESIS,
    CONF_SUMMER_THRESHOLD,
    CONF_TARGET_TEMPERATURE,
    DEFAULT_COMFORT_MAXIMUM_TEMPERATURE,
    DEFAULT_COMFORT_MINIMUM_TEMPERATURE,
    DEFAULT_MAXIMUM_SENSOR_AGE_MINUTES,
    DEFAULT_RECOVERY_VALID_OBSERVATIONS,
    DEFAULT_SUMMER_HYSTERESIS,
    DEFAULT_SUMMER_THRESHOLD,
    DEFAULT_TARGET_TEMPERATURE,
    OUTPUT_MODE_GENERIC,
    OUTPUT_MODE_OHMON_MQTT,
    OUTPUT_MODE_SHADOW,
    PLATFORMS,
    PumpSteerEntryData,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one isolated PumpSteer V3 runtime and its selected output."""
    from .v3.control.engine import ControlEngine, ControlEngineConfig
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
    from .v3.models import SafetyPolicy

    source_config = {**entry.data, **getattr(entry, "options", {})}
    indoor_entity = source_config[CONF_INDOOR_ENTITY]
    outdoor_entity = source_config[CONF_OUTDOOR_ENTITY]
    target_temperature = entry.data.get(
        CONF_TARGET_TEMPERATURE,
        DEFAULT_TARGET_TEMPERATURE,
    )
    runtime_config = RuntimeConfig(
        indoor_entity=indoor_entity,
        outdoor_entity=outdoor_entity,
        target_temperature=target_temperature,
        comfort_minimum_temperature=source_config.get(
            CONF_COMFORT_MINIMUM_TEMPERATURE,
            DEFAULT_COMFORT_MINIMUM_TEMPERATURE,
        ),
        comfort_maximum_temperature=source_config.get(
            CONF_COMFORT_MAXIMUM_TEMPERATURE,
            DEFAULT_COMFORT_MAXIMUM_TEMPERATURE,
        ),
    )
    engine = ControlEngine(
        config=ControlEngineConfig(
            summer_threshold=source_config.get(
                CONF_SUMMER_THRESHOLD, DEFAULT_SUMMER_THRESHOLD
            ),
            summer_hysteresis=source_config.get(
                CONF_SUMMER_HYSTERESIS, DEFAULT_SUMMER_HYSTERESIS
            ),
            recovery_valid_observations=int(
                source_config.get(
                    CONF_RECOVERY_VALID_OBSERVATIONS,
                    DEFAULT_RECOVERY_VALID_OBSERVATIONS,
                )
            ),
        )
    )
    safety_policy = SafetyPolicy(
        maximum_sensor_age=timedelta(
            minutes=float(
                source_config.get(
                    CONF_MAXIMUM_SENSOR_AGE_MINUTES,
                    DEFAULT_MAXIMUM_SENSOR_AGE_MINUTES,
                )
            )
        )
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
    elif output_mode == OUTPUT_MODE_GENERIC:
        from .v3.ha.generic_output import (
            GenericOutput,
            GenericOutputConfig,
            HomeAssistantPayloadRenderer,
            HomeAssistantServiceCallTransport,
        )

        output = GenericOutput(
            config=GenericOutputConfig(
                command_service=source_config.get(CONF_GOS_COMMAND_SERVICE, ""),
                command_payload_template=source_config.get(
                    CONF_GOS_COMMAND_PAYLOAD_TEMPLATE, ""
                ),
                safe_service=source_config.get(CONF_GOS_SAFE_SERVICE, ""),
                safe_payload_template=source_config.get(
                    CONF_GOS_SAFE_PAYLOAD_TEMPLATE, ""
                ),
                safe_action_confirmed=source_config.get(
                    CONF_GOS_SAFE_ACTION_CONFIRMED, False
                ),
            ),
            transport=HomeAssistantServiceCallTransport(hass),
            renderer=HomeAssistantPayloadRenderer(hass),
        )
        await output.async_initialize()
    runtime = PumpSteerRuntime(
        config=runtime_config,
        states=HomeAssistantStateProvider(hass),
        engine=engine,
        safety_policy=safety_policy,
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

    try:
        await coordinator.async_refresh()
    except Exception:
        _LOGGER.exception(
            "Initial PumpSteer runtime refresh failed; entities remain loaded for recovery"
        )
        try:
            await runtime.async_shutdown()
        except Exception:
            _LOGGER.exception(
                "Unable to request physical-output bypass after initial refresh failure"
            )

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
