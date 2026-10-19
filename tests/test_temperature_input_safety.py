"""Offline temperature qualification and dispatch interruption regressions."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_safe_mode_output import setup_sensor  # noqa: F401 -- shared HA boundary

from custom_components.pumpsteer.sensor import MODE_PI


@pytest.fixture
def control(request, monkeypatch):
    sensor, states, clock = request.getfixturevalue("setup_sensor")
    sensor._config_entry.options["aggressiveness"] = 0

    async def prices(cfg, now):
        return [1.0] * 24, ["normal"] * 24, 60, 0

    async def forecast():
        return []

    monkeypatch.setattr(sensor, "_get_prices", prices)
    monkeypatch.setattr(sensor, "_forecast_temps", forecast)
    sensor.async_write_ha_state = lambda: None
    return sensor, states, clock


def _report(states, clock, **attributes):
    for key in ("sensor.indoor", "sensor.outdoor"):
        states[key].attributes = dict(attributes)
        states[key].last_reported = clock[0]


def test_explicit_restored_numeric_not_used(control):
    sensor, states, clock = control
    _report(states, clock, restored=True)
    asyncio.run(sensor.async_update())
    assert sensor.state is None
    assert sensor.hass.services.calls == []


@pytest.mark.parametrize("metadata", ["missing", "old", "naive"])
def test_unqualified_report_rejected_after_start(control, metadata):
    sensor, states, clock = control
    asyncio.run(sensor._handle_ha_started(None))
    clock[0] += timedelta(seconds=1)
    for key in ("sensor.indoor", "sensor.outdoor"):
        if metadata == "old":
            states[key].last_reported = clock[0] - timedelta(days=1)
        elif metadata == "naive":
            states[key].last_reported = clock[0].replace(tzinfo=None)
    asyncio.run(sensor.async_update())
    assert sensor.state is None
    assert sensor.hass.services.calls == []


def test_restore_pulse_unavailable_then_unchanged_fresh_report(control):
    sensor, states, clock = control
    _report(states, clock, restored=True)
    asyncio.run(sensor._handle_ha_started(None))
    clock[0] += timedelta(seconds=1)
    _report(states, clock, restored=True)
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == []
    states["sensor.outdoor"].state = "unavailable"
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == []
    states["sensor.outdoor"].state = "-3.3"
    clock[0] += timedelta(seconds=1)
    _report(states, clock)
    for key in ("sensor.indoor", "sensor.outdoor"):
        states[key].last_changed = clock[0] - timedelta(days=1)
        states[key].last_updated = states[key].last_changed
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_PI
    assert len(sensor.hass.services.calls) == 2


@pytest.mark.parametrize("fresh_metadata", [False, True])
def test_start_requires_report_after_start_and_recovers(control, fresh_metadata):
    sensor, states, clock = control
    _report(states, clock)
    asyncio.run(sensor._handle_ha_started(None))
    assert sensor.hass.services.calls == []
    clock[0] += timedelta(seconds=1)
    if fresh_metadata:
        _report(states, clock)
    asyncio.run(sensor.async_update())
    assert len(sensor.hass.services.calls) == (2 if fresh_metadata else 0)


@pytest.mark.parametrize(
    "report_kind", ["early", "restored", "old", "at_event", "late"]
)
def test_start_qualifies_against_event_not_delayed_handler(control, report_kind):
    sensor, states, clock = control
    event = SimpleNamespace(time_fired=clock[0])
    clock[0] += timedelta(seconds=1)
    _report(states, clock, **({"restored": True} if report_kind == "restored" else {}))
    if report_kind in ("old", "at_event"):
        for key in ("sensor.indoor", "sensor.outdoor"):
            states[key].last_reported = event.time_fired - timedelta(
                seconds=1 if report_kind == "old" else 0
            )
    elif report_kind == "late":
        for key in ("sensor.indoor", "sensor.outdoor"):
            states[key].last_reported = event.time_fired
    clock[0] += timedelta(seconds=1)
    asyncio.run(sensor._handle_ha_started(event))
    assert len(sensor.hass.services.calls) == (2 if report_kind == "early" else 0)
    if report_kind == "late":
        clock[0] += timedelta(seconds=1)
        _report(states, clock)
        asyncio.run(sensor.async_update())
        assert sensor.extra_state_attributes["mode"] == MODE_PI
        assert len(sensor.hass.services.calls) == 2


@pytest.mark.parametrize("event_time", [None, "invalid", "naive", "future"])
def test_start_invalid_event_time_uses_conservative_now(control, event_time):
    sensor, states, clock = control
    if event_time == "naive":
        event_time = clock[0].replace(tzinfo=None)
    elif event_time == "future":
        event_time = clock[0] + timedelta(days=1)
    _report(states, clock)
    asyncio.run(sensor._handle_ha_started(SimpleNamespace(time_fired=event_time)))
    assert sensor.hass.services.calls == []
    clock[0] += timedelta(seconds=1)
    _report(states, clock)
    asyncio.run(sensor.async_update())
    assert len(sensor.hass.services.calls) == 2


def test_reload_waits_for_new_reports(control, monkeypatch):
    sensor, states, clock = control
    _report(states, clock)
    sensor.hass.is_running = True
    subscriptions = []
    sensor.hass.bus = SimpleNamespace(
        async_listen_once=lambda *args: subscriptions.append(args)
    )
    sensor._config_entry.add_update_listener = lambda callback: lambda: None

    async def no_extra():
        return None

    monkeypatch.setattr(sensor, "async_get_last_extra_data", no_extra, raising=False)
    asyncio.run(sensor.async_added_to_hass())
    assert sensor.hass.services.calls == []
    assert subscriptions == []  # HA is already running
    clock[0] += timedelta(seconds=1)
    _report(states, clock)
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_PI
    assert len(sensor.hass.services.calls) == 2


def test_before_ha_start_sends_nothing(control):
    sensor, _, _ = control
    sensor.hass.is_running = False
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == []


@pytest.mark.parametrize("stage", ["prices", "forecast"])
@pytest.mark.parametrize("value", ["unavailable", "unknown", "nan", "85", "-60"])
def test_loss_or_changed_input_during_calculation_aborts(
    control, monkeypatch, stage, value
):
    sensor, states, _ = control

    async def prices(cfg, now):
        states["sensor.outdoor"].state = value
        return [], [], 60, 0

    async def forecast():
        states["sensor.outdoor"].state = value
        return []

    monkeypatch.setattr(
        sensor,
        "_get_prices" if stage == "prices" else "_forecast_temps",
        prices if stage == "prices" else forecast,
    )
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == []
    assert sensor.state is None
    assert sensor.extra_state_attributes["temperature_input_status"] == "interrupted"
    assert sensor.extra_state_attributes["receiver_state"] == "unverified"


def test_loss_between_gos_and_ohmigo_blocks_second_write(control):
    sensor, states, _ = control
    calls = sensor.hass.services.calls

    async def dispatch(domain, service, data, blocking=False):
        calls.append((domain, service, data))
        states["sensor.outdoor"].state = "unavailable"

    sensor.hass.services.async_call = dispatch
    asyncio.run(sensor.async_update())
    assert len(calls) == 1
    assert calls[0][0] == "test_output"
    assert sensor._ohmigo_last_push is None
    assert sensor.state is None
    assert sensor.extra_state_attributes["temperature_input_status"] == "interrupted"


def test_unavailable_then_recovery_preserves_intervals(control):
    sensor, states, clock = control
    asyncio.run(sensor.async_update())
    calls = list(sensor.hass.services.calls)
    states["sensor.outdoor"].state = "unavailable"
    clock[0] += timedelta(seconds=1)
    asyncio.run(sensor.async_update())
    assert sensor.state is None
    assert sensor.hass.services.calls == calls
    states["sensor.outdoor"].state = "-4"
    clock[0] += timedelta(seconds=1)
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_PI
    assert sensor.hass.services.calls == calls
    clock[0] += timedelta(minutes=10)
    asyncio.run(sensor.async_update())
    assert len(sensor.hass.services.calls) == len(calls) + 2


def test_source_change_during_calculation_aborts(control, monkeypatch):
    sensor, states, _ = control
    states["sensor.other"] = SimpleNamespace(state="-3.3", attributes={})

    async def forecast():
        sensor._config_entry.options["real_outdoor_entity"] = "sensor.other"
        return []

    monkeypatch.setattr(sensor, "_forecast_temps", forecast)
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == []


def test_unload_removes_pending_start_listener(control, monkeypatch):
    sensor, _, _ = control
    sensor.hass.is_running = False
    removed = []
    sensor.hass.bus = SimpleNamespace(
        async_listen_once=lambda *args: lambda: removed.append("start")
    )
    sensor._config_entry.add_update_listener = lambda callback: (
        lambda: removed.append("options")
    )

    async def no_extra():
        return None

    monkeypatch.setattr(sensor, "async_get_last_extra_data", no_extra, raising=False)
    asyncio.run(sensor.async_added_to_hass())
    asyncio.run(sensor.async_will_remove_from_hass())
    assert sorted(removed) == ["options", "start"]


def test_unload_during_calculation_blocks_dispatch(control, monkeypatch):
    sensor, _, _ = control

    async def forecast():
        await sensor.async_will_remove_from_hass()
        return []

    monkeypatch.setattr(sensor, "_forecast_temps", forecast)
    asyncio.run(sensor.async_update())
    assert sensor.hass.services.calls == []
    assert sensor.extra_state_attributes["temperature_input_status"] == "interrupted"


def test_overlapping_updates_do_not_duplicate_output(control):
    sensor, _, _ = control

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = sensor.hass.services.calls

        async def dispatch(domain, service, data, blocking=False):
            calls.append((domain, service, data))
            if len(calls) == 1:
                started.set()
                await release.wait()

        sensor.hass.services.async_call = dispatch
        first = asyncio.create_task(sensor.async_update())
        await started.wait()
        try:
            await sensor.async_options_update_listener(
                sensor.hass, sensor._config_entry
            )
        finally:
            release.set()
            await first
        assert len(calls) == 2

    asyncio.run(scenario())


def test_update_gate_released_after_error(control, monkeypatch):
    sensor, _, _ = control

    async def failure():
        raise RuntimeError("synthetic calculation failure")

    monkeypatch.setattr(sensor, "_forecast_temps", failure)
    asyncio.run(sensor.async_update())
    assert sensor.state is None

    async def recovered():
        return []

    monkeypatch.setattr(sensor, "_forecast_temps", recovered)
    asyncio.run(sensor.async_update())
    assert sensor.extra_state_attributes["mode"] == MODE_PI
    assert len(sensor.hass.services.calls) == 2


def test_update_gate_released_after_cancellation(control, monkeypatch):
    sensor, _, _ = control

    async def scenario():
        started = asyncio.Event()
        waiting = asyncio.Event()

        async def delayed_forecast():
            started.set()
            await waiting.wait()

        monkeypatch.setattr(sensor, "_forecast_temps", delayed_forecast)
        task = asyncio.create_task(sensor.async_update())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sensor.hass.services.calls == []

        async def recovered():
            return []

        monkeypatch.setattr(sensor, "_forecast_temps", recovered)
        await sensor.async_update()
        assert sensor.extra_state_attributes["mode"] == MODE_PI
        assert len(sensor.hass.services.calls) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["prices", "forecast"])
def test_options_during_calculation_rerun_without_stale_dispatch(control, stage):
    sensor, _, _ = control
    sensor._prev_aggressiveness = 0
    sensor._pi._integral = 5.0

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        passes = []

        async def prices(cfg, now):
            passes.append(cfg.get("electricity_price_entity"))
            if len(passes) == 2:
                assert sensor.hass.services.calls == []
            if stage == "prices" and len(passes) == 1:
                started.set()
                await release.wait()
            # A stale expensive source must never reach the receiver.
            category = "expensive" if len(passes) == 1 else "normal"
            return [1.0] * 24, [category] * 24, 60, 0

        async def forecast():
            if stage == "forecast" and len(passes) == 1:
                started.set()
                await release.wait()
            return []

        sensor._get_prices = prices
        sensor._forecast_temps = forecast
        task = asyncio.create_task(sensor.async_update())
        await started.wait()
        try:
            for suffix in ("one", "two"):
                sensor._config_entry.options.update(
                    electricity_price_entity=f"sensor.price_{suffix}",
                    weather_entity=f"weather.{suffix}",
                )
                await sensor.async_options_update_listener(
                    sensor.hass, sensor._config_entry
                )
            assert sensor.hass.services.calls == []
        finally:
            release.set()
            await task
        assert passes == ["sensor.price", "sensor.price_two"]
        assert sensor._pi._integral == 5.0
        assert sensor.extra_state_attributes["mode"] == MODE_PI
        assert len(sensor.hass.services.calls) == 2
        assert sensor._ohmigo_last_push is not None

    asyncio.run(scenario())
