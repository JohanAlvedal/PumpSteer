"""Configuration and migration flow for PumpSteer V3."""

from __future__ import annotations

import math

import voluptuous as vol
from homeassistant import config_entries
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


def _entry_unique_id(indoor_entity: str, outdoor_entity: str) -> str:
    """Return a deterministic identity for one controlled sensor pair."""
    return f"{indoor_entity.strip().lower()}::{outdoor_entity.strip().lower()}"


class PumpSteerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the intentionally minimal PumpSteer V3 experience."""

    VERSION = 3
    MINOR_VERSION = 0

    async def async_step_user(self, user_input=None):
        """Collect the two critical sensors and initial room target."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_input(user_input)
            if not errors:
                unique_id = _entry_unique_id(
                    user_input[CONF_INDOOR_ENTITY],
                    user_input[CONF_OUTDOOR_ENTITY],
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
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
                    vol.Required(CONF_INDOOR_ENTITY): selector(
                        {
                            "entity": {
                                "domain": "sensor",
                                "device_class": "temperature",
                            }
                        }
                    ),
                    vol.Required(CONF_OUTDOOR_ENTITY): selector(
                        {
                            "entity": {
                                "domain": "sensor",
                                "device_class": "temperature",
                            }
                        }
                    ),
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

    def _entity_exists(self, entity_id: str) -> bool:
        """Accept registry-backed entities even while temporarily unavailable."""
        if self.hass.states.get(entity_id) is not None:
            return True
        registry = er.async_get(self.hass)
        lookup = getattr(registry, "async_get", None)
        return bool(lookup and lookup(entity_id) is not None)


async def async_migrate_entry(hass, entry: config_entries.ConfigEntry) -> bool:
    """Migrate useful V2 identity without importing old tuning parameters."""
    if entry.version >= 3:
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
        unique_id=_entry_unique_id(indoor, outdoor),
        version=3,
        minor_version=0,
    )
    return True
