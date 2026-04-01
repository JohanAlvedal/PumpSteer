"""
HA test stubs — ersätter homeassistant-moduler i testmiljö utan HA installerat.

Changelog:
  - FIX: callback-decorator tillagd i homeassistant.core (blockerade collection)
  - FIX: parse_datetime använder fromisoformat
  - FIX: as_local konverterar naive datetime till UTC
  - FIX: RestoreEntity stub med async_get_last_state
  - FIX: vol.Optional tillagd
"""

import datetime as _dt
import sys
import types

# ── homeassistant (root) ──────────────────────────────────────────────────────
ha = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", ha)

# ── config_entries ────────────────────────────────────────────────────────────
config_entries = types.ModuleType("homeassistant.config_entries")


class ConfigEntry:
    pass


class OptionsFlow:
    async def async_step_init(self, user_input=None):
        return {}


class ConfigFlow:
    """Stub för ConfigFlow — används av PumpSteerConfigFlow i control.py."""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    async def async_step_user(self, user_input=None):
        return {}

    def async_create_entry(self, title="", data=None):
        return {"title": title, "data": data or {}}

    def async_show_form(self, **kwargs):
        return {}

    @classmethod
    def async_get_options_flow(cls, config_entry):
        return None


config_entries.ConfigEntry = ConfigEntry
config_entries.OptionsFlow = OptionsFlow
config_entries.ConfigFlow = ConfigFlow
sys.modules["homeassistant.config_entries"] = config_entries

# ── core ──────────────────────────────────────────────────────────────────────
core = types.ModuleType("homeassistant.core")


class HomeAssistant:
    pass


# FIX: @callback decorator saknades — orsakade collection error
def callback(func):
    """Stub för @callback decorator från homeassistant.core."""
    return func


core.HomeAssistant = HomeAssistant
core.callback = callback
sys.modules["homeassistant.core"] = core

# ── helpers (root) ────────────────────────────────────────────────────────────
helpers = types.ModuleType("homeassistant.helpers")
sys.modules["homeassistant.helpers"] = helpers

# ── helpers.entity ────────────────────────────────────────────────────────────
entity_mod = types.ModuleType("homeassistant.helpers.entity")


class Entity:
    pass


entity_mod.Entity = Entity
sys.modules["homeassistant.helpers.entity"] = entity_mod

# ── helpers.restore_state ─────────────────────────────────────────────────────
restore_state_mod = types.ModuleType("homeassistant.helpers.restore_state")


class RestoreEntity(Entity):
    """Stub för RestoreEntity. async_get_last_state returnerar None i testmiljö."""

    async def async_added_to_hass(self) -> None:
        pass

    async def async_will_remove_from_hass(self) -> None:
        pass

    async def async_get_last_state(self):
        return None


restore_state_mod.RestoreEntity = RestoreEntity
sys.modules["homeassistant.helpers.restore_state"] = restore_state_mod

# ── helpers.event ─────────────────────────────────────────────────────────────
event_mod = types.ModuleType("homeassistant.helpers.event")


def async_track_state_change_event(hass, entity_ids, action):
    return lambda: None


event_mod.async_track_state_change_event = async_track_state_change_event
sys.modules["homeassistant.helpers.event"] = event_mod

# ── helpers.entity_registry ───────────────────────────────────────────────────
entity_registry_mod = types.ModuleType("homeassistant.helpers.entity_registry")


class EntityRegistry:
    def async_get_entity_id(self, domain, platform, unique_id):
        return None


def async_get(hass):
    return EntityRegistry()


entity_registry_mod.async_get = async_get
entity_registry_mod.EntityRegistry = EntityRegistry
sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_mod

# ── const ─────────────────────────────────────────────────────────────────────
const = types.ModuleType("homeassistant.const")
const.STATE_UNAVAILABLE = "unavailable"
const.STATE_UNKNOWN = "unknown"
const.STATE_ON = "on"
sys.modules["homeassistant.const"] = const

# ── helpers.typing ────────────────────────────────────────────────────────────
typing_mod = types.ModuleType("homeassistant.helpers.typing")
typing_mod.StateType = object
sys.modules["homeassistant.helpers.typing"] = typing_mod

# ── helpers.device_registry ───────────────────────────────────────────────────
device_registry = types.ModuleType("homeassistant.helpers.device_registry")


class DeviceInfo:
    def __init__(self, *args, **kwargs):
        pass


device_registry.DeviceInfo = DeviceInfo
sys.modules["homeassistant.helpers.device_registry"] = device_registry

# ── helpers.entity_platform ───────────────────────────────────────────────────
entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")


class AddEntitiesCallback:
    pass


entity_platform.AddEntitiesCallback = AddEntitiesCallback
sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

# ── helpers.selector ──────────────────────────────────────────────────────────
selector_mod = types.ModuleType("homeassistant.helpers.selector")


def selector(config):
    return config


selector_mod.selector = selector
sys.modules["homeassistant.helpers.selector"] = selector_mod

# ── helpers.template ──────────────────────────────────────────────────────────
template_mod = types.ModuleType("homeassistant.helpers.template")


def as_datetime(value):
    return value


template_mod.as_datetime = as_datetime
sys.modules["homeassistant.helpers.template"] = template_mod

# ── util.dt ───────────────────────────────────────────────────────────────────
util = types.ModuleType("homeassistant.util")
dt = types.ModuleType("homeassistant.util.dt")


def now():
    """Returnerar aktuell tid med UTC-timezone."""
    return _dt.datetime.now(tz=_dt.timezone.utc)


def parse_datetime(value: str):
    """FIX: Parsar ISO-format datetime-strängar korrekt."""
    if not value or not isinstance(value, str):
        return None
    try:
        return _dt.datetime.fromisoformat(value)
    except ValueError, TypeError:
        return None


def as_local(dt_obj):
    """FIX: Konverterar naive datetime till UTC i testmiljö."""
    if dt_obj is None:
        return None
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=_dt.timezone.utc)
    return dt_obj


dt.now = now
dt.parse_datetime = parse_datetime
dt.as_local = as_local
util.dt = dt
sys.modules["homeassistant.util"] = util
sys.modules["homeassistant.util.dt"] = dt

# ── voluptuous ────────────────────────────────────────────────────────────────
vol = types.ModuleType("voluptuous")


def Schema(val):
    return val


def Required(name, default=None):
    return name


def Optional(name, default=None):  # FIX: saknades tidigare
    return name


vol.Schema = Schema
vol.Required = Required
vol.Optional = Optional
sys.modules["voluptuous"] = vol

# ── numpy ─────────────────────────────────────────────────────────────────────
np_mod = types.ModuleType("numpy")


def array(x):
    return x


def percentile(arr, percentiles):
    arr = sorted(arr)
    results = []
    for p in percentiles:
        k = int(len(arr) * p / 100)
        if k >= len(arr):
            k = len(arr) - 1
        results.append(arr[k])
    return results


def select(condlist, choicelist, default=None):
    n = len(condlist[0]) if condlist else 0
    out = []
    for i in range(n):
        choice = default
        for cond, val in zip(condlist, choicelist):
            if cond[i]:
                choice = val
                break
        out.append(choice)
    return out


np_mod.array = array
np_mod.percentile = percentile
np_mod.select = select
sys.modules["numpy"] = np_mod

# ── homeassistant.components.recorder ────────────────────────────────────────
components_mod = types.ModuleType("homeassistant.components")
recorder_mod = types.ModuleType("homeassistant.components.recorder")


def get_instance(hass):
    return None


recorder_mod.get_instance = get_instance
history_mod = types.ModuleType("homeassistant.components.recorder.history")


def get_significant_states(*args, **kwargs):
    return {}


history_mod.get_significant_states = get_significant_states
recorder_mod.history = history_mod
sys.modules["homeassistant.components"] = components_mod
sys.modules["homeassistant.components.recorder"] = recorder_mod
sys.modules["homeassistant.components.recorder.history"] = history_mod
