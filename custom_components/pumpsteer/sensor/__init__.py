from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .sensor import PumpSteerSensor, is_ml_experimental_enabled


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register both control and ML analysis sensors"""
    sensor = PumpSteerSensor(hass, config_entry)
    entities = [sensor]
    if is_ml_experimental_enabled(config_entry):
        from .ml_sensor import PumpSteerMLSensor

        entities.append(PumpSteerMLSensor(hass, config_entry))
    async_add_entities(entities, update_before_add=True)
