from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .sensor import PumpSteerSensor
from .ml_sensor import PumpSteerMLSensor
from .heat_demand_sensor import HeatDemandSensor


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register control, ML analysis, and heat demand sensors."""
    sensor = PumpSteerSensor(hass, config_entry)
    ml_sensor = PumpSteerMLSensor(hass, config_entry)
    heat_demand_sensor = HeatDemandSensor(hass, config_entry)
    async_add_entities([sensor, ml_sensor, heat_demand_sensor], update_before_add=True)
