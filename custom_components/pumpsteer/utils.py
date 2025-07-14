import logging
from typing import Optional, Tuple, List, Any
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.typing import StateType

_LOGGER = logging.getLogger(__name__)

def safe_float(val: StateType) -> Optional[float]:
    """Safely convert a value to float, returning None if conversion fails"""
    try:
        if val is None:
            return None
        return float(val)
    except (TypeError, ValueError):
        return None

def get_state(hass: HomeAssistant, entity_id: str) -> Optional[str]:
    """Get entity state with improved error handling and logging"""
    if not entity_id:
        _LOGGER.debug("No entity_id provided")
        return None
    
    try:
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.warning(f"Entity {entity_id} not found")
            return None
        
        if entity.state in [STATE_UNAVAILABLE, STATE_UNKNOWN, 'unavailable', 'unknown']:
            _LOGGER.debug(f"Entity {entity_id} is {entity.state}")
            return None
        
        return entity.state
    except Exception as e:
        _LOGGER.error(f"Error getting state for {entity_id}: {e}")
        return None

def get_attr(hass: HomeAssistant, entity_id: str, attribute: str) -> Any:
    """Get entity attribute with improved error handling"""
    if not entity_id:
        _LOGGER.debug(f"No entity_id provided for attribute {attribute}")
        return None
    
    try:
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.warning(f"Entity {entity_id} not found for attribute {attribute}")
            return None
        
        if attribute not in entity.attributes:
            _LOGGER.debug(f"Attribute {attribute} not found in entity {entity_id}")
            return None
        
        return entity.attributes.get(attribute)
    except Exception as e:
        _LOGGER.error(f"Error getting attribute {attribute} for {entity_id}: {e}")
        return None

def safe_get_price_data(prices: List[Any]) -> Tuple[float, float, float]:
    """
    Safely extract current price, max price, and price factor from electricity prices.
    
    Args:
        prices: List of electricity prices (may contain None values)
    
    Returns:
        Tuple of (current_price, max_price, price_factor)
        Returns (0.0, 0.0, 0.0) if no valid prices found
    """
    if not prices or not isinstance(prices, list):
        _LOGGER.warning("No electricity prices available or invalid format")
        return 0.0, 0.0, 0.0
    
    # Filter out None values and convert to float
    valid_prices = []
    for i, price in enumerate(prices):
        if price is not None:
            try:
                valid_price = float(price)
                valid_prices.append(valid_price)
            except (ValueError, TypeError):
                _LOGGER.warning(f"Invalid price value at index {i}: {price}")
                continue
    
    if not valid_prices:
        _LOGGER.warning("No valid electricity prices found in list")
        return 0.0, 0.0, 0.0
    
    current_price = valid_prices[0]
    max_price = max(valid_prices)
    price_factor = current_price / max_price if max_price > 0 else 0.0
    
    _LOGGER.debug(f"Price data: current={current_price:.3f}, max={max_price:.3f}, factor={price_factor:.3f}")
    return current_price, max_price, price_factor

def safe_parse_temperature_forecast(hourly_temps_csv: str) -> Optional[List[float]]:
    """
    Safely parse CSV temperature forecast data.
    
    Args:
        hourly_temps_csv: Comma-separated temperature values
    
    Returns:
        List of temperatures or None if parsing fails
    """
    if not hourly_temps_csv or not isinstance(hourly_temps_csv, str):
        _LOGGER.warning("No temperature forecast data or invalid format")
        return None
    
    try:
        # Split and parse temperatures
        temp_strings = [t.strip() for t in hourly_temps_csv.split(',') if t.strip()]
        if not temp_strings:
            _LOGGER.warning("Empty temperature forecast after parsing")
            return None
        
        temperatures = []
        for i, temp_str in enumerate(temp_strings):
            try:
                temp = float(temp_str)
                # Basic sanity check for temperature values
                if temp < -50 or temp > 50:
                    _LOGGER.warning(f"Extreme temperature value at index {i}: {temp}°C")
                temperatures.append(temp)
            except (ValueError, TypeError):
                _LOGGER.warning(f"Invalid temperature value at index {i}: {temp_str}")
                continue
        
        if not temperatures:
            _LOGGER.error("No valid temperatures found in forecast")
            return None
        
        _LOGGER.debug(f"Parsed {len(temperatures)} temperature values")
        return temperatures
        
    except Exception as e:
        _LOGGER.error(f"Error parsing temperature forecast: {e}")
        return None

def validate_required_entities(hass: HomeAssistant, config: dict) -> List[str]:
    """
    Validate that all required entities exist and are available.
    
    Args:
        hass: HomeAssistant instance
        config: Configuration dictionary
    
    Returns:
        List of error messages (empty if all valid)
    """
    errors = []
    
    required_entities = {
        "indoor_temp_entity": "Indoor Temperature",
        "real_outdoor_entity": "Outdoor Temperature", 
        "target_temp_entity": "Target Temperature",
        "electricity_price_entity": "Electricity Price",
        "hourly_forecast_temperatures_entity": "Temperature Forecast"
    }
    
    for entity_key, description in required_entities.items():
        entity_id = config.get(entity_key)
        if not entity_id:
            errors.append(f"Missing required entity: {description} ({entity_key})")
            continue
        
        # Check if entity exists
        entity = hass.states.get(entity_id)
        if not entity:
            errors.append(f"Entity not found: {description} ({entity_id})")
            continue
        
        # Check if entity is available
        if entity.state in [STATE_UNAVAILABLE, STATE_UNKNOWN, 'unavailable', 'unknown']:
            errors.append(f"Entity unavailable: {description} ({entity_id})")
    
    return errors

def safe_get_entity_state_with_description(hass: HomeAssistant, entity_id: str, description: str) -> Optional[str]:
    """
    Get entity state with descriptive error messages.
    
    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID to get state from
        description: Human-readable description for error messages
    
    Returns:
        Entity state or None if unavailable
    """
    if not entity_id:
        _LOGGER.error(f"No entity_id provided for {description}")
        return None
    
    try:
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.error(f"Entity {entity_id} ({description}) not found")
            return None
        
        if entity.state in [STATE_UNAVAILABLE, STATE_UNKNOWN, 'unavailable', 'unknown']:
            _LOGGER.warning(f"Entity {entity_id} ({description}) is {entity.state}")
            return None
        
        return entity.state
    except Exception as e:
        _LOGGER.error(f"Error getting state for {entity_id} ({description}): {e}")
        return None

def safe_array_slice(array: List[Any], start: int, length: int) -> List[Any]:
    """
    Safely slice an array with bounds checking.
    
    Args:
        array: Source array
        start: Starting index
        length: Desired length
    
    Returns:
        Sliced array (may be shorter than requested length)
    """
    if not array or start < 0 or start >= len(array):
        return []
    
    end = min(start + length, len(array))
    return array[start:end]
