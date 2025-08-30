import logging
import json
from pathlib import Path
from typing import Optional, Tuple, List, Any, Union
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.typing import StateType

from .settings import (
    MIN_REASONABLE_TEMP,
    MAX_REASONABLE_TEMP,
    MIN_REASONABLE_PRICE,
    MAX_REASONABLE_PRICE,
)

_LOGGER = logging.getLogger(__name__)


def get_version() -> str:
    """Load integration version from manifest.json."""
    manifest_path = Path(__file__).resolve().parent / "manifest.json"
    try:
        with open(manifest_path) as manifest_file:
            data = json.load(manifest_file)
    except FileNotFoundError:
        _LOGGER.error("manifest.json not found at %s", manifest_path)
        return "unknown"
    except json.JSONDecodeError as err:
        _LOGGER.error("Error decoding manifest.json: %s", err)
        return "unknown"

    version = data.get("version")
    if not version:
        _LOGGER.error("Version not set in manifest.json")
        return "unknown"

    return version


def safe_float(
    val: StateType, min_val: Optional[float] = None, max_val: Optional[float] = None
) -> Optional[float]:
    """
    Safely convert value to float with optional min/max bounds.

    Args:
        val: Value to convert
        min_val: Minimum value (optional)
        max_val: Maximum value (optional)

    Returns:
        Float value or None if conversion fails
    """
    if val is None:
        return None

    try:
        float_val = float(val)

        # Check bounds if provided
        if min_val is not None and float_val < min_val:
            _LOGGER.warning(f"Value {float_val} below minimum {min_val}")
            return None

        if max_val is not None and float_val > max_val:
            _LOGGER.warning(f"Value {float_val} above maximum {max_val}")
            return None

        return float_val

    except (TypeError, ValueError) as e:
        _LOGGER.debug(f"Failed to convert '{val}' to float: {e}")
        return None


def get_state(
    hass: HomeAssistant, entity_id: str, default: Optional[str] = None
) -> Optional[str]:
    """
    Get entity state with improved error handling and logging.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID to get state from
        default: Default value if entity not found

    Returns:
        Entity state or default/None
    """
    if not entity_id:
        _LOGGER.debug("No entity_id provided")
        return default

    if not isinstance(entity_id, str):
        _LOGGER.warning(f"Invalid entity_id type: {type(entity_id)}")
        return default

    try:
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.warning(f"Entity {entity_id} not found")
            return default

        if entity.state in [
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            "unavailable",
            "unknown",
            None,
        ]:
            _LOGGER.debug(f"Entity {entity_id} is {entity.state}")
            return default

        return entity.state

    except Exception as e:
        _LOGGER.error(f"Error getting state for {entity_id}: {e}")
        return default


def get_attr(
    hass: HomeAssistant, entity_id: str, attribute: str, default: Any = None
) -> Any:
    """
    Get entity attribute with improved error handling.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID
        attribute: Attribute name
        default: Default value if attribute not found

    Returns:
        Attribute value or default
    """
    if not entity_id or not attribute:
        _LOGGER.debug(f"Missing entity_id or attribute: {entity_id}, {attribute}")
        return default

    try:
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.warning(f"Entity {entity_id} not found for attribute {attribute}")
            return default

        if not hasattr(entity, "attributes") or entity.attributes is None:
            _LOGGER.debug(f"Entity {entity_id} has no attributes")
            return default

        if attribute not in entity.attributes:
            _LOGGER.debug(f"Attribute {attribute} not found in entity {entity_id}")
            return default

        return entity.attributes.get(attribute, default)

    except Exception as e:
        _LOGGER.error(f"Error getting attribute {attribute} for {entity_id}: {e}")
        return default


def safe_get_price_data(
    prices: List[Any], current_hour: Optional[int] = None
) -> Tuple[float, float, float]:
    """
    Safely extract price data with validation.

    Args:
        prices: List of electricity prices
        current_hour: Current hour (to get current price)

    Returns:
        Tuple of (current_price, max_price, price_factor)
        where price_factor is normalized between 0 and 1 based on
        the day's minimum and maximum prices
    """
    if not prices or not isinstance(prices, list):
        _LOGGER.warning("No electricity prices available or invalid format")
        return 0.0, 0.0, 0.0

    # Convert prices while preserving indices so that current_hour refers to
    # the original position in the list.  Invalid entries are stored as None
    # and excluded from statistics, preventing index shifts.
    converted_prices: List[Optional[float]] = []
    invalid_count = 0

    for i, price in enumerate(prices):
        if price is None:
            converted_prices.append(None)
            invalid_count += 1
            continue

        try:
            price_float = float(price)

            # Basic sanity check
            if MIN_REASONABLE_PRICE <= price_float <= MAX_REASONABLE_PRICE:
                converted_prices.append(price_float)
            else:
                _LOGGER.warning(f"Extreme price at index {i}: {price_float}")
                converted_prices.append(price_float)

        except (ValueError, TypeError):
            _LOGGER.warning(f"Invalid price value at index {i}: {price}")
            converted_prices.append(None)
            invalid_count += 1

    valid_prices = [p for p in converted_prices if p is not None]

    if not valid_prices:
        _LOGGER.error("No valid electricity prices found in list")
        return 0.0, 0.0, 0.0

    if invalid_count > 0:
        _LOGGER.warning(
            f"Found {invalid_count} invalid price values in list of {len(prices)}"
        )

    # Calculate current price using the original index
    if (
        current_hour is not None
        and 0 <= current_hour < len(converted_prices)
        and converted_prices[current_hour] is not None
    ):
        current_price = converted_prices[current_hour]  # type: ignore[assignment]
    else:
        current_price = valid_prices[0]  # Fallback to first valid price
        if current_hour is not None:
            _LOGGER.warning(
                f"Invalid current_hour {current_hour} or price missing, using first price"
            )

    max_price = max(valid_prices)
    min_price = min(valid_prices)
    price_factor = current_price / max_price if max_price > 0 else 0.0

    _LOGGER.debug(
        f"Price data: current={current_price:.3f}, max={max_price:.3f}, "
        f"min={min_price:.3f}, factor={price_factor:.3f}"
    )

    return current_price, max_price, price_factor


def safe_parse_temperature_forecast(
    hourly_temps_csv: str, max_hours: Optional[int] = None
) -> Optional[List[float]]:
    """
    Safely parse CSV temperature forecast with validation.

    Args:
        hourly_temps_csv: Comma-separated temperature values
        max_hours: Maximum number of hours to parse (optional)

    Returns:
        List of temperatures or None if parsing fails
    """
    if not hourly_temps_csv or not isinstance(hourly_temps_csv, str):
        _LOGGER.warning("No temperature forecast data or invalid format")
        return None

    try:
        # Clean and split data
        temp_strings = [t.strip() for t in hourly_temps_csv.split(",") if t.strip()]
        if not temp_strings:
            _LOGGER.warning("Empty temperature forecast after parsing")
            return None

        # Limit number of hours if specified
        if max_hours is not None and max_hours > 0:
            temp_strings = temp_strings[:max_hours]

        temperatures = []
        parse_errors = []
        extreme_temps = []

        for i, temp_str in enumerate(temp_strings):
            try:
                temp = float(temp_str)

                # Sanity check for temperatures
                if temp < MIN_REASONABLE_TEMP or temp > MAX_REASONABLE_TEMP:
                    extreme_temps.append((i, temp))

                temperatures.append(temp)

            except (ValueError, TypeError) as e:
                parse_errors.append((i, temp_str, str(e)))
                continue

        # Log warnings for problems
        if parse_errors:
            _LOGGER.warning(f"Temperature parsing errors: {parse_errors}")

        if extreme_temps:
            _LOGGER.warning(f"Extreme temperature values detected: {extreme_temps}")

        if not temperatures:
            _LOGGER.error("No valid temperatures found in forecast")
            return None

        _LOGGER.debug(f"Parsed {len(temperatures)} temperature values")
        return temperatures

    except Exception as e:
        _LOGGER.error(f"Error parsing temperature forecast: {e}")
        return None


def validate_required_entities(
    hass: HomeAssistant, config: dict, strict: bool = True
) -> List[str]:
    """
    Validate that all required entities exist and are available.

    Args:
        hass: HomeAssistant instance
        config: Configuration dictionary
        strict: If True, also check entity states

    Returns:
        List of error messages (empty if all are valid)
    """
    errors = []

    required_entities = {
        "indoor_temp_entity": "Indoor Temperature",
        "real_outdoor_entity": "Outdoor Temperature",
        "target_temp_entity": "Target Temperature",
        "electricity_price_entity": "Electricity Price",
        "hourly_forecast_temperatures_entity": "Temperature Forecast",
    }

    optional_entities = {
        "summer_threshold_entity": "Summer Threshold",
        "holiday_mode_boolean_entity": "Holiday Mode Boolean",
        "holiday_start_datetime_entity": "Holiday Start DateTime",
        "holiday_end_datetime_entity": "Holiday End DateTime",
    }

    # Check required entities
    for entity_key, description in required_entities.items():
        entity_id = config.get(entity_key)
        if not entity_id:
            errors.append(f"Missing required entity: {description} ({entity_key})")
            continue

        error = _validate_single_entity(hass, entity_id, description, strict)
        if error:
            errors.append(error)

    # Check optional entities (log warnings only)
    for entity_key, description in optional_entities.items():
        entity_id = config.get(entity_key)
        if entity_id:
            error = _validate_single_entity(hass, entity_id, description, strict)
            if error:
                _LOGGER.warning(f"Optional entity issue: {error}")

    return errors


def _validate_single_entity(
    hass: HomeAssistant, entity_id: str, description: str, check_state: bool
) -> Optional[str]:
    """
    Validate a single entity.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID to validate
        description: Description for error messages
        check_state: Whether to check entity state

    Returns:
        Error message or None if OK
    """
    if not entity_id or not isinstance(entity_id, str):
        return f"Invalid entity ID for {description}: {entity_id}"

    try:
        entity = hass.states.get(entity_id)
        if not entity:
            return f"Entity not found: {description} ({entity_id})"

        if check_state and entity.state in [
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            "unavailable",
            "unknown",
        ]:
            return f"Entity unavailable: {description} ({entity_id}) - state: {entity.state}"

    except Exception as e:
        return f"Error validating entity {description} ({entity_id}): {e}"

    return None


def safe_get_entity_state_with_description(
    hass: HomeAssistant,
    entity_id: str,
    description: str,
    expected_type: Optional[type] = None,
) -> Optional[str]:
    """
    Get entity state with descriptive error messages and type checking.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID to get state from
        description: Readable description for error messages
        expected_type: Expected type for conversion (optional)

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

        if entity.state in [
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            "unavailable",
            "unknown",
            None,
        ]:
            _LOGGER.warning(f"Entity {entity_id} ({description}) is {entity.state}")
            return None

        state = entity.state

        # Type check if specified
        if expected_type is not None:
            try:
                expected_type(state)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    f"Entity {entity_id} ({description}) state '{state}' cannot be converted to {expected_type.__name__}"
                )
                return None

        return state

    except Exception as e:
        _LOGGER.error(f"Error getting state for {entity_id} ({description}): {e}")
        return None


def safe_array_slice(array: List[Any], start: int, length: int) -> List[Any]:
    """
    Safely slice an array with bounds checking.

    Args:
        array: Source array
        start: Start index
        length: Desired length

    Returns:
        Sliced array (may be shorter than requested length)
    """
    if not array or not isinstance(array, list):
        return []

    if start < 0:
        _LOGGER.warning(f"Negative start index {start}, using 0")
        start = 0

    if start >= len(array):
        _LOGGER.debug(f"Start index {start} beyond array length {len(array)}")
        return []

    if length <= 0:
        _LOGGER.warning(f"Invalid length {length}, returning empty list")
        return []

    end = min(start + length, len(array))
    result = array[start:end]

    if len(result) < length:
        _LOGGER.debug(
            f"Returned slice shorter than requested: {len(result)} < {length}"
        )

    return result


def safe_numeric_conversion(
    value: Any, target_type: type, default: Optional[Union[int, float]] = None
) -> Optional[Union[int, float]]:
    """
    Safely convert value to numeric type.

    Args:
        value: Value to convert
        target_type: Target type (int or float)
        default: Default value if conversion fails

    Returns:
        Converted value or default
    """
    if value is None:
        return default

    try:
        converted = target_type(value)
        return converted
    except (ValueError, TypeError) as e:
        _LOGGER.debug(f"Failed to convert '{value}' to {target_type.__name__}: {e}")
        return default


def log_entity_diagnostics(hass: HomeAssistant, entity_id: str) -> None:
    """
    Log diagnostic information about an entity.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID to diagnose
    """
    try:
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.debug(f"Diagnostics: Entity {entity_id} not found")
            return

        _LOGGER.debug(f"Diagnostics for {entity_id}:")
        _LOGGER.debug(f"  State: {entity.state}")
        _LOGGER.debug(f"  Domain: {entity.domain}")
        _LOGGER.debug(f"  Last changed: {entity.last_changed}")
        _LOGGER.debug(f"  Last updated: {entity.last_updated}")

        if entity.attributes:
            _LOGGER.debug(f"  Attributes: {list(entity.attributes.keys())}")
            # Log some important attributes
            for attr in ["unit_of_measurement", "device_class", "friendly_name"]:
                if attr in entity.attributes:
                    _LOGGER.debug(f"    {attr}: {entity.attributes[attr]}")

    except Exception as e:
        _LOGGER.error(f"Error in entity diagnostics for {entity_id}: {e}")


def create_error_summary(errors: List[str], max_display: int = 5) -> str:
    """
    Create a summary of errors for display.

    Args:
        errors: List of error messages
        max_display: Maximum number of errors to display

    Returns:
        Formatted error string
    """
    if not errors:
        return "No errors"

    if len(errors) <= max_display:
        return "; ".join(errors)
    else:
        displayed = errors[:max_display]
        remaining = len(errors) - max_display
        return f"{'; '.join(displayed)}; and {remaining} more..."


def validate_config_completeness(config: dict) -> Tuple[bool, List[str]]:
    """
    Validate that the configuration is complete.

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []
    required_keys = [
        "indoor_temp_entity",
        "real_outdoor_entity",
        "target_temp_entity",
        "electricity_price_entity",
    ]

    for key in required_keys:
        if not config.get(key):
            issues.append(f"Missing required config key: {key}")

    # Check that values are strings
    for key, value in config.items():
        if key.endswith("_entity") and value is not None and not isinstance(value, str):
            issues.append(f"Config key {key} should be string, got {type(value)}")

    return len(issues) == 0, issues
