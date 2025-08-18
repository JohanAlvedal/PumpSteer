import sys
import types
import datetime

ha = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", ha)

config_entries = types.ModuleType("homeassistant.config_entries")
class ConfigEntry:  # minimal stub
    pass
config_entries.ConfigEntry = ConfigEntry
class OptionsFlow:
    async def async_step_init(self, user_input=None):
        return {}
config_entries.OptionsFlow = OptionsFlow
sys.modules["homeassistant.config_entries"] = config_entries

core = types.ModuleType("homeassistant.core")
class HomeAssistant:  # minimal stub
    pass
core.HomeAssistant = HomeAssistant
sys.modules["homeassistant.core"] = core

helpers = types.ModuleType("homeassistant.helpers")
sys.modules["homeassistant.helpers"] = helpers

entity = types.ModuleType("homeassistant.helpers.entity")
class Entity:
    pass
entity.Entity = Entity
sys.modules["homeassistant.helpers.entity"] = entity

const = types.ModuleType("homeassistant.const")
const.STATE_UNAVAILABLE = "unavailable"
const.STATE_UNKNOWN = "unknown"
const.STATE_ON = "on"
sys.modules["homeassistant.const"] = const

typing_mod = types.ModuleType("homeassistant.helpers.typing")
typing_mod.StateType = object
sys.modules["homeassistant.helpers.typing"] = typing_mod

device_registry = types.ModuleType("homeassistant.helpers.device_registry")
class DeviceInfo:
    def __init__(self, *args, **kwargs):
        pass
device_registry.DeviceInfo = DeviceInfo
sys.modules["homeassistant.helpers.device_registry"] = device_registry

entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
class AddEntitiesCallback:
    pass
entity_platform.AddEntitiesCallback = AddEntitiesCallback
sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

selector_mod = types.ModuleType("homeassistant.helpers.selector")
def selector(config):
    return config
selector_mod.selector = selector
sys.modules["homeassistant.helpers.selector"] = selector_mod

template_mod = types.ModuleType("homeassistant.helpers.template")
def as_datetime(value):
    return value
template_mod.as_datetime = as_datetime
sys.modules["homeassistant.helpers.template"] = template_mod

util = types.ModuleType("homeassistant.util")
dt = types.ModuleType("homeassistant.util.dt")
def now():
    return datetime.datetime.now()
dt.now = now
util.dt = dt
sys.modules["homeassistant.util"] = util
sys.modules["homeassistant.util.dt"] = dt

vol = types.ModuleType("voluptuous")
def Schema(val):
    return val
def Required(name, default=None):
    return name
vol.Schema = Schema
vol.Required = Required
sys.modules["voluptuous"] = vol

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
