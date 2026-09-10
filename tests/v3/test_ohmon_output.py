"""Safety-contract tests for the V3 OhmOnWiFi MQTT output adapter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from custom_components.pumpsteer.v3 import ControlDecision, ControlState, ReasonCode
from custom_components.pumpsteer.v3.control.supervisor import SupervisedOutput
from custom_components.pumpsteer.v3.ha.ohmon_output import (
    OhmonMqttConfig,
    OhmonMqttOutput,
    OhmonOutputError,
    OhmonOutputState,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeTransport:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, int, bool]] = []
        self.fail_payloads: set[str] = set()

    async def async_publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        if payload in self.fail_payloads:
            raise RuntimeError(f"simulated publish failure: {payload}")
        self.messages.append((topic, payload, qos, retain))


def config() -> OhmonMqttConfig:
    return OhmonMqttConfig(
        base_topic="ohmonwifiplus/123456/",
        watchdog_confirmed=True,
    )


def supervised(value: float, *, fallback: bool = False) -> SupervisedOutput:
    decision = ControlDecision.create(
        decided_at=NOW,
        state=ControlState.FAILSAFE if fallback else ControlState.COMFORT,
        outdoor_temperature=value,
        reason_codes=(
            ReasonCode.CRITICAL_SENSOR_INVALID
            if fallback
            else ReasonCode.COMFORT_WITHIN_BAND,
        ),
    )
    return SupervisedOutput(
        decision=decision,
        apply_physical=True,
        constraints=(),
        fallback_active=fallback,
    )


def test_active_writes_temperature_before_relay_watchdog() -> None:
    transport = FakeTransport()
    output = OhmonMqttOutput(config=config(), transport=transport)

    asyncio.run(output.async_publish(supervised(2.26)))

    assert transport.messages == [
        ("ohmonwifiplus/123456/temperature/set", "2.50", 1, False),
        ("ohmonwifiplus/123456/relay/set", "ON", 1, False),
    ]
    assert output.snapshot.state is OhmonOutputState.ACTIVE_COMMAND_SENT
    assert output.snapshot.commanded_temperature == 2.5


def test_startup_fallback_and_shutdown_explicitly_request_bypass() -> None:
    transport = FakeTransport()
    output = OhmonMqttOutput(config=config(), transport=transport)

    asyncio.run(output.async_initialize())
    asyncio.run(output.async_publish(supervised(-5, fallback=True)))
    asyncio.run(output.async_shutdown())

    assert [message[1] for message in transport.messages] == ["OFF", "OFF", "OFF"]
    assert output.snapshot.state is OhmonOutputState.BYPASS_REQUESTED


def test_publish_failure_attempts_bypass_and_reports_fault() -> None:
    transport = FakeTransport()
    transport.fail_payloads.add("ON")
    output = OhmonMqttOutput(config=config(), transport=transport)

    with pytest.raises(OhmonOutputError, match="simulated publish failure"):
        asyncio.run(output.async_publish(supervised(1.0)))

    assert transport.messages == [
        ("ohmonwifiplus/123456/temperature/set", "1.00", 1, False),
        ("ohmonwifiplus/123456/relay/set", "OFF", 1, False),
    ]
    assert output.snapshot.state is OhmonOutputState.FAULT
    assert output.snapshot.publish_count == 2
    assert output.snapshot.last_error is not None

    transport.fail_payloads.clear()
    with pytest.raises(OhmonOutputError, match="fault-latched"):
        asyncio.run(output.async_publish(supervised(2.0)))
    assert [message[1] for message in transport.messages] == ["1.00", "OFF", "OFF"]


def test_failed_startup_or_shutdown_never_claims_bypass() -> None:
    startup_transport = FakeTransport()
    startup_transport.fail_payloads.add("OFF")
    startup = OhmonMqttOutput(config=config(), transport=startup_transport)

    with pytest.raises(OhmonOutputError, match="OFF"):
        asyncio.run(startup.async_initialize())
    assert startup.snapshot.state is OhmonOutputState.FAULT

    shutdown_transport = FakeTransport()
    shutdown = OhmonMqttOutput(config=config(), transport=shutdown_transport)
    asyncio.run(shutdown.async_publish(supervised(1.0)))
    shutdown_transport.fail_payloads.add("OFF")

    with pytest.raises(OhmonOutputError, match="OFF"):
        asyncio.run(shutdown.async_shutdown())
    assert shutdown.snapshot.state is OhmonOutputState.FAULT
    assert shutdown.snapshot.publish_count == 2


def test_adapter_rejects_shadow_authority_and_out_of_range_output() -> None:
    transport = FakeTransport()
    output = OhmonMqttOutput(config=config(), transport=transport)
    shadow = SupervisedOutput(
        decision=supervised(0).decision,
        apply_physical=False,
        constraints=(),
    )

    with pytest.raises(ValueError, match="physical authorization"):
        asyncio.run(output.async_publish(shadow))
    with pytest.raises(OhmonOutputError, match="outside"):
        asyncio.run(output.async_publish(supervised(31)))
    assert transport.messages[-1][1] == "OFF"


@pytest.mark.parametrize(
    "base_topic",
    ["", "ohmon/#/", "ohmon/+/", "ohmon/device", "ohmon/device id/"],
)
def test_config_rejects_ambiguous_or_unsafe_topics(base_topic: str) -> None:
    with pytest.raises(ValueError, match="base_topic"):
        OhmonMqttConfig(base_topic=base_topic, watchdog_confirmed=True)


def test_config_refuses_active_control_without_confirmed_watchdog() -> None:
    with pytest.raises(ValueError, match="watchdog"):
        OhmonMqttConfig(
            base_topic="ohmonwifiplus/123456/",
            watchdog_confirmed=False,
        )
