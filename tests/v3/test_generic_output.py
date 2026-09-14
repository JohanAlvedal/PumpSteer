"""Safety-contract tests for the V3 Generic Output System adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from custom_components.pumpsteer.v3 import ControlDecision, ControlState, ReasonCode
from custom_components.pumpsteer.v3.control.supervisor import SupervisedOutput
from custom_components.pumpsteer.v3.ha.generic_output import (
    GenericOutput,
    GenericOutputConfig,
    GenericOutputError,
    GenericOutputState,
    HomeAssistantServiceCallTransport,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_services: set[str] = set()
        self.hang_services: set[str] = set()

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: Mapping[str, Any],
    ) -> None:
        target = f"{domain}.{service}"
        if target in self.hang_services:
            await asyncio.Event().wait()
        if target in self.fail_services:
            raise RuntimeError(f"simulated service failure: {target}")
        self.calls.append((domain, service, dict(service_data)))


class FakeRenderer:
    def render(
        self,
        source: str,
        variables: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if source.startswith("INVALID"):
            raise ValueError("simulated template failure")
        if source == "COMMAND {{ fake_temp }}":
            return {
                "entity_id": "number.virtual_outdoor",
                "value": variables["fake_temp"],
            }
        return {
            "entity_id": "switch.physical_sensor_bypass",
            "reason": variables["safe_reason"],
            "fallback_temperature": variables["fake_temp"],
        }


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeFeedback:
    def __init__(self, acknowledged: bool) -> None:
        self.acknowledged = acknowledged
        self.expected: list[float] = []

    async def async_verify(self, expected_temperature: float) -> bool:
        self.expected.append(expected_temperature)
        return self.acknowledged


class FakeServiceRegistry:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls: list[tuple[str, str, dict[str, Any], bool]] = []

    def has_service(self, domain: str, service: str) -> bool:
        return self.available

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any],
        *,
        blocking: bool,
    ) -> None:
        self.calls.append((domain, service, service_data, blocking))


class FakeHass:
    def __init__(self, services: FakeServiceRegistry) -> None:
        self.services = services


def config(**changes: Any) -> GenericOutputConfig:
    values = {
        "command_service": "number.set_value",
        "command_payload_template": "COMMAND {{ fake_temp }}",
        "safe_service": "switch.turn_off",
        "safe_payload_template": "SAFE",
        "safe_action_confirmed": True,
        "minimum_write_interval": timedelta(minutes=1),
        "watchdog_timeout": timedelta(minutes=3),
    }
    values.update(changes)
    return GenericOutputConfig(**values)


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


@pytest.mark.asyncio
async def test_active_call_uses_only_supervised_rounded_temperature() -> None:
    transport = FakeTransport()
    output = GenericOutput(
        config=config(),
        transport=transport,
        renderer=FakeRenderer(),
    )

    await output.async_publish(supervised(2.26))

    assert transport.calls == [
        (
            "number",
            "set_value",
            {"entity_id": "number.virtual_outdoor", "value": 2.5},
        )
    ]
    assert output.snapshot.state is GenericOutputState.ACTIVE_COMMAND_SENT
    assert output.snapshot.commanded_temperature == 2.5
    assert output.snapshot.acknowledged is None


@pytest.mark.asyncio
async def test_home_assistant_transport_requires_available_blocking_action() -> None:
    services = FakeServiceRegistry()
    transport = HomeAssistantServiceCallTransport(
        FakeHass(services)  # type: ignore[arg-type]
    )

    await transport.async_call("number", "set_value", {"value": 1.5})

    assert services.calls == [
        ("number", "set_value", {"value": 1.5}, True),
    ]

    unavailable = HomeAssistantServiceCallTransport(  # type: ignore[arg-type]
        FakeHass(FakeServiceRegistry(available=False))
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        await unavailable.async_call("number", "set_value", {"value": 1.5})


@pytest.mark.asyncio
async def test_startup_fallback_and_shutdown_always_request_safe_action() -> None:
    transport = FakeTransport()
    output = GenericOutput(
        config=config(),
        transport=transport,
        renderer=FakeRenderer(),
    )

    await output.async_initialize()
    await output.async_publish(supervised(-5.0, fallback=True))
    await output.async_shutdown()

    assert [(domain, service) for domain, service, _ in transport.calls] == [
        ("switch", "turn_off"),
        ("switch", "turn_off"),
        ("switch", "turn_off"),
    ]
    assert [payload["reason"] for _, _, payload in transport.calls] == [
        "initialize",
        "controller_fallback",
        "shutdown",
    ]
    assert transport.calls[1][2]["fallback_temperature"] == -5.0
    assert output.snapshot.state is GenericOutputState.SAFE_ACTION_REQUESTED


@pytest.mark.asyncio
async def test_failed_startup_or_shutdown_never_claims_safe_state() -> None:
    startup_transport = FakeTransport()
    startup_transport.fail_services.add("switch.turn_off")
    startup = GenericOutput(
        config=config(),
        transport=startup_transport,
        renderer=FakeRenderer(),
    )
    with pytest.raises(GenericOutputError, match="simulated service failure"):
        await startup.async_initialize()
    assert startup.snapshot.state is GenericOutputState.FAULT

    shutdown_transport = FakeTransport()
    shutdown = GenericOutput(
        config=config(),
        transport=shutdown_transport,
        renderer=FakeRenderer(),
    )
    await shutdown.async_publish(supervised(1.0))
    shutdown_transport.fail_services.add("switch.turn_off")
    with pytest.raises(GenericOutputError, match="simulated service failure"):
        await shutdown.async_shutdown()
    assert shutdown.snapshot.state is GenericOutputState.FAULT


@pytest.mark.asyncio
async def test_write_failure_requests_safe_action_and_latches_fault() -> None:
    transport = FakeTransport()
    transport.fail_services.add("number.set_value")
    output = GenericOutput(
        config=config(),
        transport=transport,
        renderer=FakeRenderer(),
    )

    with pytest.raises(GenericOutputError, match="simulated service failure"):
        await output.async_publish(supervised(1.0))

    assert transport.calls == [
        (
            "switch",
            "turn_off",
            {
                "entity_id": "switch.physical_sensor_bypass",
                "reason": "write_failure",
                "fallback_temperature": None,
            },
        )
    ]
    assert output.snapshot.state is GenericOutputState.FAULT

    transport.fail_services.clear()
    with pytest.raises(GenericOutputError, match="fault-latched"):
        await output.async_publish(supervised(2.0))
    assert transport.calls[-1][2]["reason"] == "fault_latched"


@pytest.mark.asyncio
async def test_template_or_feedback_failure_cannot_leave_command_active() -> None:
    template_transport = FakeTransport()
    template_output = GenericOutput(
        config=config(command_payload_template="INVALID fake_temp"),
        transport=template_transport,
        renderer=FakeRenderer(),
    )

    with pytest.raises(GenericOutputError, match="template failure"):
        await template_output.async_publish(supervised(1.0))
    assert template_transport.calls[-1][1] == "turn_off"
    assert template_output.snapshot.state is GenericOutputState.FAULT

    feedback_transport = FakeTransport()
    feedback = FakeFeedback(acknowledged=False)
    feedback_output = GenericOutput(
        config=config(),
        transport=feedback_transport,
        renderer=FakeRenderer(),
        feedback=feedback,
    )
    with pytest.raises(GenericOutputError, match="did not acknowledge"):
        await feedback_output.async_publish(supervised(1.0))
    assert feedback.expected == [1.0]
    assert feedback_transport.calls[-1][1] == "turn_off"
    assert feedback_output.snapshot.state is GenericOutputState.FAULT


@pytest.mark.asyncio
async def test_feedback_is_never_implied_when_not_configured() -> None:
    transport = FakeTransport()
    feedback = FakeFeedback(acknowledged=True)
    output = GenericOutput(
        config=config(),
        transport=transport,
        renderer=FakeRenderer(),
        feedback=feedback,
    )

    await output.async_publish(supervised(1.0))

    assert feedback.expected == [1.0]
    assert output.snapshot.state is GenericOutputState.ACTIVE_COMMAND_ACKNOWLEDGED
    assert output.snapshot.acknowledged is True


@pytest.mark.asyncio
async def test_interval_limits_normal_calls_but_never_safe_actions() -> None:
    transport = FakeTransport()
    clock = FakeClock()
    output = GenericOutput(
        config=config(minimum_write_interval=timedelta(seconds=60)),
        transport=transport,
        renderer=FakeRenderer(),
        monotonic=clock,
    )

    await output.async_publish(supervised(1.0))
    clock.advance(30)
    await output.async_publish(supervised(2.0))
    assert len(transport.calls) == 1
    assert output.snapshot.state is GenericOutputState.ACTIVE_COMMAND_INTERVAL_LIMITED

    await output.async_publish(supervised(2.0, fallback=True))
    assert transport.calls[-1][1] == "turn_off"

    clock.advance(30)
    await output.async_publish(supervised(2.0))
    assert transport.calls[-1][0:2] == ("number", "set_value")


@pytest.mark.asyncio
async def test_bounded_call_timeout_requests_safe_action() -> None:
    transport = FakeTransport()
    transport.hang_services.add("number.set_value")
    output = GenericOutput(
        config=config(service_call_timeout=timedelta(milliseconds=10)),
        transport=transport,
        renderer=FakeRenderer(),
    )

    with pytest.raises(GenericOutputError, match="TimeoutError"):
        await output.async_publish(supervised(1.0))

    assert transport.calls[-1][1] == "turn_off"
    assert output.snapshot.state is GenericOutputState.FAULT


@pytest.mark.asyncio
async def test_watchdog_requests_safe_action_when_control_cycles_stop() -> None:
    transport = FakeTransport()
    output = GenericOutput(
        config=config(watchdog_timeout=timedelta(milliseconds=20)),
        transport=transport,
        renderer=FakeRenderer(),
    )
    await output.async_initialize()
    await output.async_publish(supervised(1.0))

    for _ in range(20):
        if output.snapshot.state is GenericOutputState.FAULT:
            break
        await asyncio.sleep(0.01)

    assert output.snapshot.state is GenericOutputState.FAULT
    assert output.snapshot.last_error is not None
    assert "watchdog expired" in output.snapshot.last_error
    assert transport.calls[-1][1] == "turn_off"
    assert transport.calls[-1][2]["reason"] == "watchdog_timeout"
    await output.async_shutdown()


@pytest.mark.asyncio
async def test_adapter_rejects_shadow_wrong_type_and_out_of_range_output() -> None:
    transport = FakeTransport()
    output = GenericOutput(
        config=config(),
        transport=transport,
        renderer=FakeRenderer(),
    )
    shadow = SupervisedOutput(
        decision=supervised(0).decision,
        apply_physical=False,
        constraints=(),
    )

    with pytest.raises(TypeError, match="only SupervisedOutput"):
        await output.async_publish(1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="physical authorization"):
        await output.async_publish(shadow)
    with pytest.raises(GenericOutputError, match="outside"):
        await output.async_publish(supervised(31.0))
    assert transport.calls[-1][1] == "turn_off"


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("command_service", "set_value", "domain.service"),
        ("command_service", "number.Set Value", "domain.service"),
        ("safe_service", "", "domain.service"),
        ("command_payload_template", "value: 1", "fake_temp"),
        ("safe_payload_template", "", "non-empty"),
        ("safe_action_confirmed", False, "explicitly confirmed"),
        ("watchdog_timeout", timedelta(0), "positive"),
    ],
)
def test_config_rejects_incomplete_or_unsafe_contract(
    field: str,
    value: Any,
    match: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=match):
        config(**{field: value})
