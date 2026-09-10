"""Configuration and migration flow for PumpSteer V3."""

from __future__ import annotations

import math
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import selector

from .const import (
    CONF_INDOOR_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_TARGET_TEMPERATURE,
    DEFAULT_TARGET_TEMPERATURE,
    DOMAIN,
    MAX_TARGET_TEMPERATURE,
    MIN_TARGET_TEMPERATURE,
)

LEGACY_OUTDOOR_ENTITY = "real_outdoor_entity"


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
        return errors

    def _entity_exists(self, entity_id: str) -> bool:
        """Accept registry-backed entities even while temporarily unavailable."""
        if self.hass.states.get(entity_id) is not None:
            return True
        registry = er.async_get(self.hass)
        lookup = getattr(registry, "async_get", None)
        return bool(lookup and lookup(entity_id) is not None)


async def async_migrate_entry(hass, entry: config_entries.ConfigEntry) -> bool:
    """Migrate useful V2 identity without importing old tuning parameters."""
    if entry.version > 3:
        return False
    if entry.version == 3 and entry.minor_version >= 1:
        return True
    if entry.version == 3:
        hass.config_entries.async_update_entry(
            entry,
            unique_id=_entry_unique_id(entry.entry_id),
            version=3,
            minor_version=1,
        )
        return True
    legacy = {**entry.data, **entry.options}
    indoor = legacy.get(CONF_INDOOR_ENTITY)
    outdoor = legacy.get(CONF_OUTDOOR_ENTITY) or legacy.get(LEGACY_OUTDOOR_ENTITY)
    if not indoor or not outdoor:
        return False
    try:
        target = float(legacy.get(CONF_TARGET_TEMPERATURE, DEFAULT_TARGET_TEMPERATURE))
    except (TypeError, ValueError):
        target = DEFAULT_TARGET_TEMPERATURE
    if not math.isfinite(target) or not (
        MIN_TARGET_TEMPERATURE <= target <= MAX_TARGET_TEMPERATURE
    ):
        target = DEFAULT_TARGET_TEMPERATURE
    hass.config_entries.async_update_entry(
        entry,
        data={
            CONF_INDOOR_ENTITY: indoor,
            CONF_OUTDOOR_ENTITY: outdoor,
            CONF_TARGET_TEMPERATURE: target,
        },
        options={},
        unique_id=_entry_unique_id(entry.entry_id),
        version=3,
        minor_version=1,
    )
    return True
