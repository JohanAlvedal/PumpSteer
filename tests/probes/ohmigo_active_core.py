"""Isolated real-Core service/event test; no integration or hardware deployment."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from importlib.metadata import version

from homeassistant.core import HomeAssistant
from homeassistant import bootstrap, loader
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from custom_components.pumpsteer import relay_guard  # noqa: E402
from custom_components.pumpsteer.sensor import PumpSteerSensor  # noqa: E402


async def main():
    config = Path(sys.argv[1]).resolve()
    config.mkdir(exist_ok=False)
    hass = HomeAssistant(str(config))
    loader.async_setup(hass)
    hass.config.skip_pip = True
    assert (
        await bootstrap.async_from_config_dict(
            {
                "homeassistant": {
                    "name": "Isolated safety probe",
                    "latitude": 0,
                    "longitude": 0,
                    "elevation": 0,
                    "time_zone": "UTC",
                }
            },
            hass,
        )
        is hass
    )
    entry = SimpleNamespace(
        entry_id="isolated",
        data={},
        options={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "ohmigo_entity": "number.receiver",
            "ohmigo_relay_entity": "switch.relay",
            "ohmigo_interval_minutes": 5,
            "aggressiveness": 0,
        },
    )
    registry = er.async_get(hass)
    await registry.async_load()
    for key, object_id in (("ohmigo_enabled", "push"), ("ohmigo_relay_guard", "guard")):
        entity = registry.async_get_or_create(
            "switch", "pumpsteer", f"isolated_{key}", suggested_object_id=object_id
        )
        hass.states.async_set(entity.entity_id, "on")
    hass.states.async_set("switch.relay", "off")
    guard = relay_guard.OhmigoRelayGuard(hass, entry, "switch.relay")
    hass.data["pumpsteer"] = {entry.entry_id: {"relay_guard": guard}}
    sensor = PumpSteerSensor(hass, entry)
    sensor.async_write_ha_state = lambda: None

    async def prices(*args):
        return [1.0] * 24, ["normal"] * 24, 60, 0

    async def forecast():
        return []

    sensor._get_prices = prices
    sensor._forecast_temps = forecast
    calls = []
    applied = [None]
    fail = [False]

    async def number(call):
        await asyncio.sleep(0)  # real awaited HA handler boundary
        if fail[0]:
            raise HomeAssistantError("isolated simulated delivery failure")
        applied[0] = call.data["value"]
        calls.append("number_applied")
        hass.states.async_set("number.receiver", str(applied[0]))

    async def active(call):
        assert applied[0] is not None
        calls.append("ACTIVE")
        hass.states.async_set("switch.relay", "on")

    hass.services.async_register("number", "set_value", number)
    hass.services.async_register("switch", "turn_on", active)
    # Only recovery sleep durations are accelerated; real HA service scheduling.
    relay_guard._STABILIZE_SECONDS = 0
    relay_guard._VERIFY_SECONDS = 0
    assert version("homeassistant") == "2026.10.1"
    result = {"core_version": version("homeassistant"), "scenarios": []}
    try:
        await hass.async_start()
        guard.async_start()
        await hass.async_block_till_done()
        assert calls == []
        await sensor._handle_ha_started(None)
        assert calls == []
        result["scenarios"].append("startup_without_sources_no_commands")

        for entity, value in (("sensor.indoor", "21"), ("sensor.outdoor", "-3.3")):
            hass.states.async_set(entity, value, {"unit_of_measurement": "°C"})
        await sensor.async_update()
        await hass.async_block_till_done()
        assert calls == ["number_applied", "ACTIVE"], calls
        result["scenarios"].append("awaited_number_handler_before_ACTIVE")

        before = list(calls)
        hass.states.async_set("sensor.outdoor", "unavailable")
        await sensor.async_update()
        hass.states.async_set("switch.relay", "off")
        await hass.async_block_till_done()
        assert calls == before
        hass.states.async_set("sensor.outdoor", "-3.3", {"unit_of_measurement": "°C"})
        await sensor.async_update()
        await hass.async_block_till_done()
        assert calls == before
        result["scenarios"].append("loss_recovery_before_interval_no_old_ACTIVE")

        sensor._ohmigo_last_push = None  # force due interval, test boundary only
        fail[0] = True
        await sensor.async_update()
        await hass.async_block_till_done()
        assert calls == before
        result["scenarios"].append("awaited_number_service_error_no_ACTIVE")

        fail[0] = False
        await sensor.async_update()
        await hass.async_block_till_done()
        assert calls == before + ["number_applied", "ACTIVE"]
        result["scenarios"].append("next_successful_write_requalifies")
        result["calls"] = calls
        result["physical_ack_verified"] = False
        print(json.dumps(result, indent=2))
    finally:
        await guard.async_stop()
        await hass.async_stop()


asyncio.run(main())
