import asyncio
from pathlib import Path

from custom_components.pumpsteer import ohmigo


class _FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append(
            {
                "domain": domain,
                "service": service,
                "data": data,
                "blocking": blocking,
            }
        )


class _FakeHass:
    def __init__(self):
        self.services = _FakeServices()


class _FakeEntry:
    def __init__(self, options):
        self.entry_id = "test-entry"
        self.data = {}
        self.options = options


class _FakeTemplate:
    def __init__(self, template_text, hass):
        self.template_text = template_text
        self.hass = hass

    def async_render(self, variables):
        return {"value": round(variables["fake_temp"], 1)}


def test_gos_options_fields_are_exposed():
    """Keep all legacy GOS option keys visible in the options flow."""
    source = Path("custom_components/pumpsteer/options_flow.py").read_text()

    assert '"modbus_service"' in source
    assert '"modbus_payload_template"' in source
    assert '"modbus_interval_minutes"' in source
    assert '"suggested_value": current_data.get("weather_entity")' in source


def test_async_push_modbus_calls_configured_service(monkeypatch):
    """Render fake_temp and forward the resulting mapping to the HA service."""
    template_module = __import__(
        "homeassistant.helpers.template", fromlist=["Template"]
    )
    monkeypatch.setattr(template_module, "Template", _FakeTemplate, raising=False)

    hass = _FakeHass()
    entry = _FakeEntry(
        {
            "modbus_service": "modbus.write_register",
            "modbus_payload_template": 'value: "{{ fake_temp }}"',
            "modbus_interval_minutes": 5,
        }
    )

    last_push = asyncio.run(
        ohmigo.async_push_modbus(hass, entry, 7.26, last_push_time=None)
    )

    assert last_push is not None
    assert hass.services.calls == [
        {
            "domain": "modbus",
            "service": "write_register",
            "data": {"value": 7.3},
            "blocking": False,
        }
    ]


def test_gos_runs_without_ohmigo_entity(monkeypatch):
    """GOS must run independently when no Ohmigo output is configured."""
    template_module = __import__(
        "homeassistant.helpers.template", fromlist=["Template"]
    )
    monkeypatch.setattr(template_module, "Template", _FakeTemplate, raising=False)

    ohmigo._modbus_last_push_by_entry.clear()
    hass = _FakeHass()
    entry = _FakeEntry(
        {
            "ohmigo_entity": "",
            "modbus_service": "input_number.set_value",
            "modbus_payload_template": 'value: "{{ fake_temp }}"',
            "modbus_interval_minutes": 5,
        }
    )

    ohmigo_last_push = asyncio.run(
        ohmigo.async_push_ohmigo(hass, entry, -3.44, last_push_time=None)
    )

    assert ohmigo_last_push is None
    assert hass.services.calls == [
        {
            "domain": "input_number",
            "service": "set_value",
            "data": {"value": -3.4},
            "blocking": False,
        }
    ]
