import logging
from typing import Optional, Tuple, List, Any, Union
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.typing import StateType

_LOGGER = logging.getLogger(__name__)

# Konstanter för validering
MIN_REASONABLE_TEMP = -50.0
MAX_REASONABLE_TEMP = 60.0
MIN_REASONABLE_PRICE = -2.0  # Negativa priser kan förekomma
MAX_REASONABLE_PRICE = 15.0


def safe_float(
    val: StateType, min_val: Optional[float] = None, max_val: Optional[float] = None
) -> Optional[float]:
    """
    Säkert konvertera värde till float med valfria gränsvärden.

    Args:
        val: Värde att konvertera
        min_val: Minimivärde (valfritt)
        max_val: Maximivärde (valfritt)

    Returns:
        Float-värde eller None om konvertering misslyckas
    """
    if val is None:
        return None

    try:
        float_val = float(val)

        # Kontrollera gränsvärden om de anges
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
    Hämta entity state med förbättrad felhantering och loggning.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID att hämta state från
        default: Standardvärde om entity inte finns

    Returns:
        Entity state eller default/None
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
    Hämta entity attribut med förbättrad felhantering.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID
        attribute: Attributnamn
        default: Standardvärde om attribut inte finns

    Returns:
        Attributvärde eller default
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
    Säkert extrahera prisdata med validering.

    Args:
        prices: Lista med elpriser
        current_hour: Aktuell timme (för att hämta nuvarande pris)

    Returns:
        Tuple med (current_price, max_price, price_factor)
    """
    if not prices or not isinstance(prices, list):
        _LOGGER.warning("No electricity prices available or invalid format")
        return 0.0, 0.0, 0.0

    # Filtrera och konvertera till giltiga priser
    valid_prices = []
    invalid_count = 0

    for i, price in enumerate(prices):
        if price is not None:
            try:
                price_float = float(price)

                # Grundläggande sanity check
                if MIN_REASONABLE_PRICE <= price_float <= MAX_REASONABLE_PRICE:
                    valid_prices.append(price_float)
                else:
                    _LOGGER.warning(f"Extreme price at index {i}: {price_float}")
                    valid_prices.append(price_float)  # Behåll ändå för beräkningar

            except (ValueError, TypeError):
                _LOGGER.warning(f"Invalid price value at index {i}: {price}")
                invalid_count += 1
                continue
        else:
            invalid_count += 1

    if not valid_prices:
        _LOGGER.error("No valid electricity prices found in list")
        return 0.0, 0.0, 0.0

    if invalid_count > 0:
        _LOGGER.warning(
            f"Found {invalid_count} invalid price values in list of {len(prices)}"
        )

    # Beräkna aktuellt pris
    if current_hour is not None and 0 <= current_hour < len(valid_prices):
        current_price = valid_prices[current_hour]
    else:
        current_price = valid_prices[0]  # Fallback till första priset
        if current_hour is not None:
            _LOGGER.warning(f"Invalid current_hour {current_hour}, using first price")

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
    Säkert parsa CSV temperaturprognos med validering.

    Args:
        hourly_temps_csv: Komma-separerade temperaturvärden
        max_hours: Maximalt antal timmar att parsa (valfritt)

    Returns:
        Lista med temperaturer eller None om parsing misslyckas
    """
    if not hourly_temps_csv or not isinstance(hourly_temps_csv, str):
        _LOGGER.warning("No temperature forecast data or invalid format")
        return None

    try:
        # Rensa och splitta data
        temp_strings = [t.strip() for t in hourly_temps_csv.split(",") if t.strip()]
        if not temp_strings:
            _LOGGER.warning("Empty temperature forecast after parsing")
            return None

        # Begränsa antal timmar om angivet
        if max_hours is not None and max_hours > 0:
            temp_strings = temp_strings[:max_hours]

        temperatures = []
        parse_errors = []
        extreme_temps = []

        for i, temp_str in enumerate(temp_strings):
            try:
                temp = float(temp_str)

                # Sanity check för temperaturer
                if temp < MIN_REASONABLE_TEMP or temp > MAX_REASONABLE_TEMP:
                    extreme_temps.append((i, temp))

                temperatures.append(temp)

            except (ValueError, TypeError) as e:
                parse_errors.append((i, temp_str, str(e)))
                continue

        # Logga varningar för problem
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
    Validera att alla nödvändiga entities finns och är tillgängliga.

    Args:
        hass: HomeAssistant instance
        config: Konfigurationsdictionary
        strict: Om True, kontrollera även entity states

    Returns:
        Lista med felmeddelanden (tom om alla är giltiga)
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

    # Kontrollera nödvändiga entities
    for entity_key, description in required_entities.items():
        entity_id = config.get(entity_key)
        if not entity_id:
            errors.append(f"Missing required entity: {description} ({entity_key})")
            continue

        error = _validate_single_entity(hass, entity_id, description, strict)
        if error:
            errors.append(error)

    # Kontrollera valfria entities (logga bara varningar)
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
    Validera en enskild entity.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID att validera
        description: Beskrivning för felmeddelanden
        check_state: Om entity state ska kontrolleras

    Returns:
        Felmeddelande eller None om OK
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
    Hämta entity state med beskrivande felmeddelanden och typkontroll.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID att hämta state från
        description: Läsbar beskrivning för felmeddelanden
        expected_type: Förväntad typ för konvertering (valfritt)

    Returns:
        Entity state eller None om otillgänglig
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

        # Typkontroll om angiven
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
    Säkert slice:a en array med bounds checking.

    Args:
        array: Källarray
        start: Startindex
        length: Önskad längd

    Returns:
        Slice:ad array (kan vara kortare än begärd längd)
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
    Säkert konvertera värde till numerisk typ.

    Args:
        value: Värde att konvertera
        target_type: Måltyp (int eller float)
        default: Standardvärde om konvertering misslyckas

    Returns:
        Konverterat värde eller default
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
    Logga diagnostisk information om en entity.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID att diagnostisera
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
            # Logga några viktiga attribut
            for attr in ["unit_of_measurement", "device_class", "friendly_name"]:
                if attr in entity.attributes:
                    _LOGGER.debug(f"    {attr}: {entity.attributes[attr]}")

    except Exception as e:
        _LOGGER.error(f"Error in entity diagnostics for {entity_id}: {e}")


def create_error_summary(errors: List[str], max_display: int = 5) -> str:
    """
    Skapa en sammanfattning av fel för visning.

    Args:
        errors: Lista med felmeddelanden
        max_display: Maximalt antal fel att visa

    Returns:
        Formaterad felsträng
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
    Validera att konfigurationen är komplett.

    Args:
        config: Konfigurationsdictionary

    Returns:
        Tuple med (is_valid, list_of_issues)
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

    # Kontrollera att värden är strängar
    for key, value in config.items():
        if key.endswith("_entity") and value is not None and not isinstance(value, str):
            issues.append(f"Config key {key} should be string, got {type(value)}")

    return len(issues) == 0, issues
