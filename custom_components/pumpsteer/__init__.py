"""PumpSteer integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging

from .options_flow import PumpSteerOptionsFlowHandler

# Importera ML-tjänster med try/except för säkerhet
try:
    from .ml_config_helper import PumpSteerMLServices
    ML_SERVICES_AVAILABLE = True
except ImportError:
    ML_SERVICES_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)
DOMAIN = "pumpsteer"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sätt upp PumpSteer integration."""
    # Sätt upp sensor-plattformen
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    
    # Sätt upp ML-tjänster om tillgängliga
    if ML_SERVICES_AVAILABLE:
        try:
            ml_services = PumpSteerMLServices(hass)
            await ml_services.async_setup_services()
            
            # Spara ML-tjänster i hass.data för senare användning
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN]['ml_services'] = ml_services
            
            _LOGGER.info("PumpSteer: ML services setup completed")
        except Exception as e:
            _LOGGER.warning(f"PumpSteer: Failed to setup ML services: {e}")
            # Fortsätt ändå utan ML-tjänster
    else:
        _LOGGER.info("PumpSteer: ML services not available, running without enhanced ML features")
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avlasta PumpSteer integration."""
    # Ta bort ML-tjänster om de finns
    if DOMAIN in hass.data and 'ml_services' in hass.data[DOMAIN]:
        try:
            ml_services = hass.data[DOMAIN]['ml_services']
            await ml_services.async_remove_services()
            _LOGGER.info("PumpSteer: ML services removed")
        except Exception as e:
            _LOGGER.warning(f"PumpSteer: Error removing ML services: {e}")
        
        # Rensa data
        hass.data[DOMAIN].pop('ml_services', None)
        if not hass.data[DOMAIN]:  # Ta bort domain-key om tom
            hass.data.pop(DOMAIN, None)
    
    # Avlasta sensor-plattformen
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])

async def async_get_options_flow(config_entry):
    """Returnera options flow handler."""
    return PumpSteerOptionsFlowHandler(config_entry)

# """PumpSteer integration."""
# from homeassistant.config_entries import ConfigEntry
# from homeassistant.core import HomeAssistant

# from .options_flow import PumpSteerOptionsFlowHandler

# DOMAIN = "pumpsteer"

# async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
#     return True

# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     return await hass.config_entries.async_unload_platforms(entry, ["sensor"])

# async def async_get_options_flow(config_entry):
#     return PumpSteerOptionsFlowHandler(config_entry)
    
# from .ml_config_helper import PumpSteerMLServices

# async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    
#     # Sätt upp ML-tjänster
#     ml_services = PumpSteerMLServices(hass)
#     await ml_services.async_setup_services()
#     hass.data.setdefault(DOMAIN, {})
#     hass.data[DOMAIN]['ml_services'] = ml_services
    
#     return True
