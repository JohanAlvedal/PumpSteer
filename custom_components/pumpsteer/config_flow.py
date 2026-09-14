"""Configuration and migration flow for PumpSteer V3."""

from __future__ import annotations

import math
import re
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import selector

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
    DOMAIN,
    MAX_TARGET_TEMPERATURE,
    MIN_TARGET_TEMPERATURE,
    OUTPUT_MODE_GENERIC,
    OUTPUT_MODE_OHMON_MQTT,
    OUTPUT_MODE_SHADOW,
)

_SERVICE_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def _entry_unique_id(entry_identity: str) -> str:
    """Return a stable identity that is independent of editable sensor sources."""
    identity = entry_identity.strip().lower()
    if not identity:
        raise ValueError("entry_identity must be a non-empty string")
    return f"pumpsteer-v3:{identity}"


def _effective_sensor_pair(entry) -> tuple[str | None, str | None]:
    """Return the active sensor pair, including option overrides."""
    effective = {**entry.data, **entry.options}
    return (
        effective.get(CONF_INDOOR_ENTITY),
        effective.get(CONF_OUTDOOR_ENTITY),
    )


def _sensor_pair_is_configured(
    hass,
    indoor_entity: str,
    outdoor_entity: str,
    *,
    exclude_entry_id: str | None = None,
) -> bool:
    """Return whether another PumpSteer entry already owns the sensor pair."""
    async_entries = getattr(
        getattr(hass, "config_entries", None), "async_entries", None
    )
    if async_entries is None:
        return False
    wanted = (indoor_entity.strip().lower(), outdoor_entity.strip().lower())
    for entry in async_entries(DOMAIN):
        if getattr(entry, "entry_id", None) == exclude_entry_id:
            continue
        indoor, outdoor = _effective_sensor_pair(entry)
        if not indoor or not outdoor:
            continue
        existing = (indoor.strip().lower(), outdoor.strip().lower())
        if existing == wanted:
            return True
    return False


def _temperature_entity_selector():
    """Return the shared selector for temperature source entities."""
    return selector(
        {
            "entity": {
                "domain": "sensor",
                "device_class": "temperature",
            }
        }
    )


class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the intentionally minimal PumpSteer V3 experience."""

    VERSION = 3
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow used by the integration Configure button."""
        del config_entry
        return PumpSteerOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Collect the two critical sensors and initial room target."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_input(user_input)
            if not errors and _sensor_pair_is_configured(
                self.hass,
                user_input[CONF_INDOOR_ENTITY],
                user_input[CONF_OUTDOOR_ENTITY],
            ):
                errors["base"] = "already_configured"
            if not errors:
                await self.async_set_unique_id(_entry_unique_id(uuid4().hex))
                return self.async_create_entry(
                    title="PumpSteer",
                    data={
                        CONF_INDOOR_ENTITY: user_input[CONF_INDOOR_ENTITY],
                        CONF_OUTDOOR_ENTITY: user_input[CONF_OUTDOOR_ENTITY],
                        CONF_TARGET_TEMPERATURE: float(
                            user_input[CONF_TARGET_TEMPERATURE]
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INDOOR_ENTITY): _temperature_entity_selector(),
                    vol.Required(CONF_OUTDOOR_ENTITY): _temperature_entity_selector(),
                    vol.Required(
                        CONF_TARGET_TEMPERATURE,
                        default=DEFAULT_TARGET_TEMPERATURE,
                    ): selector(
                        {
                            "number": {
                                "min": MIN_TARGET_TEMPERATURE,
                                "max": MAX_TARGET_TEMPERATURE,
                                "step": 0.5,
                                "unit_of_measurement": "°C",
                                "mode": "box",
                            }
                        }
                    ),
                }
            ),
            errors=errors,
        )

    def _validate_input(self, user_input: dict) -> dict[str, str]:
        errors = self._validate_sensor_input(user_input)
        try:
            target = float(user_input.get(CONF_TARGET_TEMPERATURE))
        except (TypeError, ValueError):
            errors[CONF_TARGET_TEMPERATURE] = "invalid_target"
        else:
            if not math.isfinite(target) or not (
                MIN_TARGET_TEMPERATURE <= target <= MAX_TARGET_TEMPERATURE
            ):
                errors[CONF_TARGET_TEMPERATURE] = "invalid_target"
        return errors

    def _validate_sensor_input(self, user_input: dict) -> dict[str, str]:
        errors: dict[str, str] = {}
        indoor = user_input.get(CONF_INDOOR_ENTITY)
        outdoor = user_input.get(CONF_OUTDOOR_ENTITY)
        if indoor == outdoor and indoor:
            errors[CONF_OUTDOOR_ENTITY] = "same_sensor"
        for field, entity_id in (
            (CONF_INDOOR_ENTITY, indoor),
            (CONF_OUTDOOR_ENTITY, outdoor),
        ):
            if not entity_id:
                errors[field] = "required"
            elif not self._entity_exists(entity_id):
                errors[field] = "entity_not_found"
        return errors

    def _entity_exists(self, entity_id: str) -> bool:
        """Accept registry-backed entities even while temporarily unavailable."""
        if self.hass.states.get(entity_id) is not None:
            return True
        registry = er.async_get(self.hass)
        lookup = getattr(registry, "async_get", None)
        return bool(lookup and lookup(entity_id) is not None)


class PumpSteerOptionsFlow(config_entries.OptionsFlow):
    """Allow source sensors to be changed after initial setup."""

    async def async_step_init(self, user_input=None):
        """Configure the Home Assistant sensor sources used by PumpSteer."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_input(user_input)
            if not errors and _sensor_pair_is_configured(
                self.hass,
                user_input[CONF_INDOOR_ENTITY],
                user_input[CONF_OUTDOOR_ENTITY],
                exclude_entry_id=getattr(self.config_entry, "entry_id", None),
            ):
                errors["base"] = "already_configured"
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        **self.config_entry.options,
                        CONF_INDOOR_ENTITY: user_input[CONF_INDOOR_ENTITY],
                        CONF_OUTDOOR_ENTITY: user_input[CONF_OUTDOOR_ENTITY],
                        CONF_OUTPUT_MODE: user_input.get(
                            CONF_OUTPUT_MODE, OUTPUT_MODE_SHADOW
                        ),
                        CONF_COMFORT_MINIMUM_TEMPERATURE: float(
                            user_input.get(
                                CONF_COMFORT_MINIMUM_TEMPERATURE,
                                DEFAULT_COMFORT_MINIMUM_TEMPERATURE,
                            )
                        ),
                        CONF_COMFORT_MAXIMUM_TEMPERATURE: float(
                            user_input.get(
                                CONF_COMFORT_MAXIMUM_TEMPERATURE,
                                DEFAULT_COMFORT_MAXIMUM_TEMPERATURE,
                            )
                        ),
                        CONF_SUMMER_THRESHOLD: float(
                            user_input.get(
                                CONF_SUMMER_THRESHOLD, DEFAULT_SUMMER_THRESHOLD
                            )
                        ),
                        CONF_SUMMER_HYSTERESIS: float(
                            user_input.get(
                                CONF_SUMMER_HYSTERESIS, DEFAULT_SUMMER_HYSTERESIS
                            )
                        ),
                        CONF_MAXIMUM_SENSOR_AGE_MINUTES: int(
                            user_input.get(
                                CONF_MAXIMUM_SENSOR_AGE_MINUTES,
                                DEFAULT_MAXIMUM_SENSOR_AGE_MINUTES,
                            )
                        ),
                        CONF_RECOVERY_VALID_OBSERVATIONS: int(
                            user_input.get(
                                CONF_RECOVERY_VALID_OBSERVATIONS,
                                DEFAULT_RECOVERY_VALID_OBSERVATIONS,
                            )
                        ),
                        CONF_OHMON_MQTT_BASE_TOPIC: user_input.get(
                            CONF_OHMON_MQTT_BASE_TOPIC, ""
                        ).strip(),
                        CONF_OHMON_WATCHDOG_CONFIRMED: bool(
                            user_input.get(CONF_OHMON_WATCHDOG_CONFIRMED, False)
                        )
                        if user_input.get(CONF_OUTPUT_MODE) == OUTPUT_MODE_OHMON_MQTT
                        else False,
                        CONF_GOS_COMMAND_SERVICE: user_input.get(
                            CONF_GOS_COMMAND_SERVICE, ""
                        ).strip(),
                        CONF_GOS_COMMAND_PAYLOAD_TEMPLATE: user_input.get(
                            CONF_GOS_COMMAND_PAYLOAD_TEMPLATE, ""
                        ).strip(),
                        CONF_GOS_SAFE_SERVICE: user_input.get(
                            CONF_GOS_SAFE_SERVICE, ""
                        ).strip(),
                        CONF_GOS_SAFE_PAYLOAD_TEMPLATE: user_input.get(
                            CONF_GOS_SAFE_PAYLOAD_TEMPLATE, ""
                        ).strip(),
                        CONF_GOS_SAFE_ACTION_CONFIRMED: bool(
                            user_input.get(CONF_GOS_SAFE_ACTION_CONFIRMED, False)
                        )
                        if user_input.get(CONF_OUTPUT_MODE) == OUTPUT_MODE_GENERIC
                        else False,
                    },
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INDOOR_ENTITY,
                        default=self._current_value(CONF_INDOOR_ENTITY),
                    ): _temperature_entity_selector(),
                    vol.Required(
                        CONF_OUTDOOR_ENTITY,
                        default=self._current_value(CONF_OUTDOOR_ENTITY),
                    ): _temperature_entity_selector(),
                    vol.Required(
                        CONF_OUTPUT_MODE,
                        default=self._current_value(CONF_OUTPUT_MODE)
                        or OUTPUT_MODE_SHADOW,
                    ): selector(
                        {
                            "select": {
                                "options": [
                                    OUTPUT_MODE_SHADOW,
                                    OUTPUT_MODE_OHMON_MQTT,
                                    OUTPUT_MODE_GENERIC,
                                ],
                                "translation_key": CONF_OUTPUT_MODE,
                                "mode": "dropdown",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_COMFORT_MINIMUM_TEMPERATURE,
                        default=self._current_value(CONF_COMFORT_MINIMUM_TEMPERATURE)
                        or DEFAULT_COMFORT_MINIMUM_TEMPERATURE,
                    ): selector(
                        {
                            "number": {
                                "min": MIN_TARGET_TEMPERATURE,
                                "max": MAX_TARGET_TEMPERATURE,
                                "step": 0.5,
                                "unit_of_measurement": "°C",
                                "mode": "box",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_COMFORT_MAXIMUM_TEMPERATURE,
                        default=self._current_value(CONF_COMFORT_MAXIMUM_TEMPERATURE)
                        or DEFAULT_COMFORT_MAXIMUM_TEMPERATURE,
                    ): selector(
                        {
                            "number": {
                                "min": MIN_TARGET_TEMPERATURE,
                                "max": MAX_TARGET_TEMPERATURE,
                                "step": 0.5,
                                "unit_of_measurement": "°C",
                                "mode": "box",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_SUMMER_THRESHOLD,
                        default=self._current_value(CONF_SUMMER_THRESHOLD)
                        or DEFAULT_SUMMER_THRESHOLD,
                    ): selector(
                        {
                            "number": {
                                "min": 5,
                                "max": 30,
                                "step": 0.5,
                                "unit_of_measurement": "°C",
                                "mode": "box",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_SUMMER_HYSTERESIS,
                        default=self._current_value(CONF_SUMMER_HYSTERESIS)
                        or DEFAULT_SUMMER_HYSTERESIS,
                    ): selector(
                        {
                            "number": {
                                "min": 0.5,
                                "max": 5,
                                "step": 0.5,
                                "unit_of_measurement": "°C",
                                "mode": "box",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_MAXIMUM_SENSOR_AGE_MINUTES,
                        default=self._current_value(CONF_MAXIMUM_SENSOR_AGE_MINUTES)
                        or DEFAULT_MAXIMUM_SENSOR_AGE_MINUTES,
                    ): selector(
                        {
                            "number": {
                                "min": 2,
                                "max": 30,
                                "step": 1,
                                "unit_of_measurement": "min",
                                "mode": "box",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_RECOVERY_VALID_OBSERVATIONS,
                        default=self._current_value(CONF_RECOVERY_VALID_OBSERVATIONS)
                        or DEFAULT_RECOVERY_VALID_OBSERVATIONS,
                    ): selector(
                        {
                            "number": {
                                "min": 2,
                                "max": 10,
                                "step": 1,
                                "mode": "box",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_OHMON_MQTT_BASE_TOPIC,
                        default=self._current_value(CONF_OHMON_MQTT_BASE_TOPIC) or "",
                    ): selector({"text": {"type": "text"}}),
                    vol.Optional(
                        CONF_OHMON_WATCHDOG_CONFIRMED,
                        default=bool(
                            self._current_value(CONF_OHMON_WATCHDOG_CONFIRMED)
                        ),
                    ): selector({"boolean": {}}),
                    vol.Optional(
                        CONF_GOS_COMMAND_SERVICE,
                        default=self._current_value(CONF_GOS_COMMAND_SERVICE) or "",
                    ): selector({"text": {"type": "text"}}),
                    vol.Optional(
                        CONF_GOS_COMMAND_PAYLOAD_TEMPLATE,
                        default=self._current_value(CONF_GOS_COMMAND_PAYLOAD_TEMPLATE)
                        or "",
                    ): selector({"text": {"multiline": True}}),
                    vol.Optional(
                        CONF_GOS_SAFE_SERVICE,
                        default=self._current_value(CONF_GOS_SAFE_SERVICE) or "",
                    ): selector({"text": {"type": "text"}}),
                    vol.Optional(
                        CONF_GOS_SAFE_PAYLOAD_TEMPLATE,
                        default=self._current_value(CONF_GOS_SAFE_PAYLOAD_TEMPLATE)
                        or "",
                    ): selector({"text": {"multiline": True}}),
                    vol.Optional(
                        CONF_GOS_SAFE_ACTION_CONFIRMED,
                        default=bool(
                            self._current_value(CONF_GOS_SAFE_ACTION_CONFIRMED)
                        ),
                    ): selector({"boolean": {}}),
                }
            ),
            errors=errors,
        )

    def _current_value(self, key: str):
        """Prefer a saved option override and otherwise use initial entry data."""
        return self.config_entry.options.get(key, self.config_entry.data.get(key))

    def _validate_input(self, user_input: dict) -> dict[str, str]:
        """Validate source changes with the same rules used during setup."""
        errors: dict[str, str] = {}
        indoor = user_input.get(CONF_INDOOR_ENTITY)
        outdoor = user_input.get(CONF_OUTDOOR_ENTITY)
        if indoor == outdoor and indoor:
            errors[CONF_OUTDOOR_ENTITY] = "same_sensor"
        for field, entity_id in (
            (CONF_INDOOR_ENTITY, indoor),
            (CONF_OUTDOOR_ENTITY, outdoor),
        ):
            if not entity_id:
                errors[field] = "required"
            elif not self._entity_exists(entity_id):
                errors[field] = "entity_not_found"
        output_mode = user_input.get(CONF_OUTPUT_MODE, OUTPUT_MODE_SHADOW)
        if output_mode not in {
            OUTPUT_MODE_SHADOW,
            OUTPUT_MODE_OHMON_MQTT,
            OUTPUT_MODE_GENERIC,
        }:
            errors[CONF_OUTPUT_MODE] = "invalid_output_mode"
        elif output_mode == OUTPUT_MODE_OHMON_MQTT:
            base_topic = user_input.get(CONF_OHMON_MQTT_BASE_TOPIC, "")
            if not isinstance(base_topic, str) or (
                not base_topic.strip()
                or not base_topic.strip().endswith("/")
                or "+" in base_topic
                or "#" in base_topic
                or any(character.isspace() for character in base_topic.strip())
            ):
                errors[CONF_OHMON_MQTT_BASE_TOPIC] = "invalid_mqtt_topic"
            if user_input.get(CONF_OHMON_WATCHDOG_CONFIRMED) is not True:
                errors[CONF_OHMON_WATCHDOG_CONFIRMED] = "watchdog_required"
        elif output_mode == OUTPUT_MODE_GENERIC:
            command_service = user_input.get(CONF_GOS_COMMAND_SERVICE, "")
            safe_service = user_input.get(CONF_GOS_SAFE_SERVICE, "")
            command_template = user_input.get(CONF_GOS_COMMAND_PAYLOAD_TEMPLATE, "")
            safe_template = user_input.get(CONF_GOS_SAFE_PAYLOAD_TEMPLATE, "")
            if not isinstance(command_service, str) or not _SERVICE_PATTERN.fullmatch(
                command_service.strip()
            ):
                errors[CONF_GOS_COMMAND_SERVICE] = "invalid_service"
            if (
                not isinstance(command_template, str)
                or not command_template.strip()
                or "fake_temp" not in command_template
            ):
                errors[CONF_GOS_COMMAND_PAYLOAD_TEMPLATE] = "invalid_gos_template"
            if not isinstance(safe_service, str) or not _SERVICE_PATTERN.fullmatch(
                safe_service.strip()
            ):
                errors[CONF_GOS_SAFE_SERVICE] = "invalid_service"
            if not isinstance(safe_template, str) or not safe_template.strip():
                errors[CONF_GOS_SAFE_PAYLOAD_TEMPLATE] = "invalid_safe_template"
            if user_input.get(CONF_GOS_SAFE_ACTION_CONFIRMED) is not True:
                errors[CONF_GOS_SAFE_ACTION_CONFIRMED] = "safe_action_required"
        numeric_fields = (
            (CONF_COMFORT_MINIMUM_TEMPERATURE, 5.0, 35.0),
            (CONF_COMFORT_MAXIMUM_TEMPERATURE, 5.0, 35.0),
            (CONF_SUMMER_THRESHOLD, 5.0, 30.0),
            (CONF_SUMMER_HYSTERESIS, 0.5, 5.0),
            (CONF_MAXIMUM_SENSOR_AGE_MINUTES, 2.0, 30.0),
            (CONF_RECOVERY_VALID_OBSERVATIONS, 2.0, 10.0),
        )
        values: dict[str, float] = {}
        defaults = {
            CONF_COMFORT_MINIMUM_TEMPERATURE: DEFAULT_COMFORT_MINIMUM_TEMPERATURE,
            CONF_COMFORT_MAXIMUM_TEMPERATURE: DEFAULT_COMFORT_MAXIMUM_TEMPERATURE,
            CONF_SUMMER_THRESHOLD: DEFAULT_SUMMER_THRESHOLD,
            CONF_SUMMER_HYSTERESIS: DEFAULT_SUMMER_HYSTERESIS,
            CONF_MAXIMUM_SENSOR_AGE_MINUTES: DEFAULT_MAXIMUM_SENSOR_AGE_MINUTES,
            CONF_RECOVERY_VALID_OBSERVATIONS: DEFAULT_RECOVERY_VALID_OBSERVATIONS,
        }
        for field, lower, upper in numeric_fields:
            try:
                value = float(user_input.get(field, defaults[field]))
            except (TypeError, ValueError):
                errors[field] = "invalid_advanced_value"
                continue
            if not math.isfinite(value) or not lower <= value <= upper:
                errors[field] = "invalid_advanced_value"
                continue
            values[field] = value
        if (
            CONF_COMFORT_MINIMUM_TEMPERATURE in values
            and CONF_COMFORT_MAXIMUM_TEMPERATURE in values
            and values[CONF_COMFORT_MINIMUM_TEMPERATURE]
            >= values[CONF_COMFORT_MAXIMUM_TEMPERATURE]
        ):
            errors[CONF_COMFORT_MAXIMUM_TEMPERATURE] = "invalid_comfort_range"
        for field in (
            CONF_MAXIMUM_SENSOR_AGE_MINUTES,
            CONF_RECOVERY_VALID_OBSERVATIONS,
        ):
            if field in values and not values[field].is_integer():
                errors[field] = "invalid_advanced_value"
        return errors

    def _entity_exists(self, entity_id: str) -> bool:
        """Accept registry-backed entities even while temporarily unavailable."""
        if self.hass.states.get(entity_id) is not None:
            return True
        registry = er.async_get(self.hass)
        lookup = getattr(registry, "async_get", None)
        return bool(lookup and lookup(entity_id) is not None)


async def async_migrate_entry(hass, entry: config_entries.ConfigEntry) -> bool:
    """Migrate V3 alpha entries without mutating a user's V2 installation."""
    if entry.version > 3:
        return False
    # V3 beta is intentionally side-by-side/test-install only. Converting a V2
    # entry here would destroy options that V2 needs for rollback. A future
    # migration must be explicit, versioned, and preserve a restorable copy.
    if entry.version < 3:
        return False
    if entry.version == 3 and entry.minor_version >= 1:
        return True
    hass.config_entries.async_update_entry(
        entry,
        unique_id=_entry_unique_id(entry.entry_id),
        version=3,
        minor_version=1,
    )
    return True
