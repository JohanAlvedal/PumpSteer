"""Exercise safe-mode output through real sensor and output code, offline."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.pumpsteer import ohmigo
from custom_components.pumpsteer.sensor import MODE_PI, MODE_SAFE, PumpSteerSensor


class _Services:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


class _Template:
    """Replace HA's template engine at the external boundary."""

    def __init__(self, text, hass):
        assert text == "{{ {'value': fake_temp} }}"

    def async_render(self, variables):
        return {"value": variables["fake_temp"]}


@pytest.fixture
def setup_sensor(monkeypatch):
    clock = [datetime(2026, 10, 11, 12, tzinfo=timezone.utc)]
    states = {
        "sensor.indoor": SimpleNamespace(state="21", attributes={}),
        "sensor.outdoor": SimpleNamespace(state="-3.3", attributes={}),
        "switch.push": SimpleNamespace(state="on", attributes={}),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), services=_Services())
    entry = SimpleNamespace(
        entry_id="safe-mode-test",
        data={},
        options={
            "indoor_temp_entity": "sensor.indoor",
            "real_outdoor_entity": "sensor.outdoor",
            "electricity_price_entity": "sensor.price",
            "ohmigo_entity": "number.ohmigo_test",
            "ohmigo_interval_minutes": 5,
            "modbus_service": "test_output.set_value",
            "modbus_payload_template": "{{ {'value': fake_temp} }}",
            "modbus_interval_minutes": 7,
        },
    )
    registry = SimpleNamespace(
        async_get_entity_id=lambda platform, domain, unique_id: (
            "switch.push" if unique_id.endswith("_ohmigo_enabled") else None
        )
    )
    monkeypatch.setattr(ohmigo.er, "async_get", lambda hass: registry)
    monkeypatch.setattr(ohmigo.dt_util, "now", lambda: clock[0])
    monkeypatch.setattr(ohmigo, "_modbus_last_push_by_entry", {})
    template_module = __import__(
        "homeassistant.helpers.template", fromlist=["Template"]
    )
    monkeypatch.setattr(template_module, "Template", _Template, raising=False)
    return PumpSteerSensor(hass, entry), states, clock


@pytest.mark.parametrize("missing", ["indoor", "prices"])
@pytest.mark.parametrize("outputs", ["ohmigo", "gos", "both"])
@pytest.mark.parametrize("push_enabled", [True, False])
@pytest.mark.parametrize("outdoor", ["-3.3", "0"])
def test_safe_mode_forwards_valid_outdoor(
    setup_sensor, missing, outputs, push_enabled, outdoor
):
    sensor, states, clock = setup_sensor
    states["sensor.outdoor"].state = outdoor
    states["switch.push"].state = "on" if push_enabled else "off"
    if missing == "indoor":
        states.pop("sensor.indoor")
    if outputs == "ohmigo":
        sensor._config_entry.options.pop("modbus_service")
    if outputs == "gos":
        sensor._config_entry.options.pop("ohmigo_entity")

    asyncio.run(sensor.async_update())

    assert sensor.extra_state_attributes["mode"] == MODE_SAFE
    assert sensor.state == float(outdoor)
    expected = []
    if outputs in ("gos", "both"):
        expected.append(("test_output", "set_value", {"value": float(outdoor)}))
    if outputs in ("ohmigo", "both") and push_enabled:
        expected.append(
            (
                "number",
                "set_value",
                {
                    "entity_id": "number.ohmigo_test",
                    "value": -3.5 if outdoor == "-3.3" else 0.0,
                },
            )
        )
    assert sensor.hass.services.calls == expected
    assert sensor._ohmigo_last_push == (
        clock[0] if outputs in ("ohmigo", "both") and push_enabled else None
    )


@pytest.mark.parametrize(
    "outdoor", [None, "unknown", "unavailable", "invalid", "nan", "inf", "-inf"]
)
def test_safe_mode_without_valid_outdoor_sends_nothing(setup_sensor, outdoor):
    sensor, states, _ = setup_sensor
    sensor._state = -12.0  # A previous control value must not be sent either.
    if outdoor is None:
        states.pop("sensor.outdoor")
    else:
        states["sensor.outdoor"].state = outdoor

    asyncio.run(sensor.async_update())

    assert sensor.extra_state_attributes["mode"] == MODE_SAFE
    assert sensor.state is None
    assert sensor.hass.services.calls == []
    assert sensor._ohmigo_last_push is None
    assert ohmigo._modbus_last_push_by_entry == {}


def test_safe_mode_preserves_independent_output_intervals(setup_sensor):
    sensor, states, clock = setup_sensor
    asyncio.run(sensor._set_state(-12, MODE_PI, {}, clock[0]))
    states.pop("sensor.indoor")
    sensor.hass.services.calls.clear()

    clock[0] += timedelta(minutes=4)
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == []

    clock[0] += timedelta(minutes=1)
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == [
        ("number", "set_value", {"entity_id": "number.ohmigo_test", "value": -3.5})
    ]

    clock[0] += timedelta(minutes=2)
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls[-1] == (
        "test_output",
        "set_value",
        {"value": -3.3},
    )
    assert len(sensor.hass.services.calls) == 2

    clock[0] += timedelta(minutes=3)
    asyncio.run(sensor.async_update())
    assert len(sensor.hass.services.calls) == 3
    assert sensor._ohmigo_last_push == clock[0]
