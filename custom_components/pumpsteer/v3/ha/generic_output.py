"""Fail-safe Generic Output System adapter for Home Assistant services."""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

import yaml
from homeassistant.core import HomeAssistant

from ..control.supervisor import SupervisedOutput

_SERVICE_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


class GenericOutputState(StrEnum):
    """Physical GOS state, separate from the controller mode."""

    SAFE_ACTION_REQUESTED = "safe_action_requested"
    ACTIVE_COMMAND_SENT = "active_command_sent"
    ACTIVE_COMMAND_ACKNOWLEDGED = "active_command_acknowledged"
    ACTIVE_COMMAND_INTERVAL_LIMITED = "active_command_interval_limited"
    FAULT = "fault"


@dataclass(frozen=True, slots=True)
class GenericOutputConfig:
    """Validated service and safety contract for one generic output."""

    command_service: str
    command_payload_template: str
    safe_service: str
    safe_payload_template: str
    safe_action_confirmed: bool
    minimum_temperature: float = -30.0
    maximum_temperature: float = 30.0
    rounding_step: float = 0.5
    minimum_write_interval: timedelta = timedelta(minutes=1)
    watchdog_timeout: timedelta = timedelta(minutes=3)
    service_call_timeout: timedelta = timedelta(seconds=10)
    feedback_timeout: timedelta = timedelta(seconds=10)

    def __post_init__(self) -> None:
        for name in ("command_service", "safe_service"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SERVICE_PATTERN.fullmatch(
                value.strip()
            ):
                raise ValueError(f"{name} must use the form domain.service")
            object.__setattr__(self, name, value.strip())
        for name in ("command_payload_template", "safe_payload_template"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty template")
            object.__setattr__(self, name, value.strip())
        if "fake_temp" not in self.command_payload_template:
            raise ValueError("command_payload_template must reference fake_temp")
        if self.safe_action_confirmed is not True:
            raise ValueError("the GOS safe action must be explicitly confirmed")
        for name in (
            "minimum_temperature",
            "maximum_temperature",
            "rounding_step",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, numeric)
        if self.minimum_temperature >= self.maximum_temperature:
            raise ValueError("minimum_temperature must be below maximum_temperature")
        if self.rounding_step <= 0:
            raise ValueError("rounding_step must be positive")
        for name in (
            "minimum_write_interval",
            "watchdog_timeout",
            "service_call_timeout",
            "feedback_timeout",
        ):
            value = getattr(self, name)
            if not isinstance(value, timedelta):
                raise TypeError(f"{name} must be a timedelta")
            if value <= timedelta(0):
                raise ValueError(f"{name} must be positive")

    @property
    def command_target(self) -> tuple[str, str]:
        """Return the validated command domain and service."""
        domain, service = self.command_service.split(".", 1)
        return domain, service

    @property
    def safe_target(self) -> tuple[str, str]:
        """Return the validated safe-action domain and service."""
        domain, service = self.safe_service.split(".", 1)
        return domain, service


class ServiceCallTransport(Protocol):
    """Minimal blocking-service boundary used by the GOS adapter."""

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: Mapping[str, Any],
    ) -> None:
        """Complete one blocking service call or raise on failure."""


class PayloadRenderer(Protocol):
    """Render one user-owned payload template into service data."""

    def render(
        self,
        source: str,
        variables: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return a string-keyed mapping or raise if rendering is invalid."""


class OutputFeedback(Protocol):
    """Optional acknowledgement boundary for a physical output value."""

    async def async_verify(self, expected_temperature: float) -> bool:
        """Return whether explicit device feedback confirms the value."""


class HomeAssistantServiceCallTransport:
    """Perform blocking calls through Home Assistant's service registry."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: Mapping[str, Any],
    ) -> None:
        has_service = getattr(self._hass.services, "has_service", None)
        if has_service is not None and not has_service(domain, service):
            raise RuntimeError(
                f"Home Assistant action is unavailable: {domain}.{service}"
            )
        await self._hass.services.async_call(
            domain,
            service,
            dict(service_data),
            blocking=True,
        )


class HomeAssistantPayloadRenderer:
    """Render Home Assistant templates and parse their YAML mapping output."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def render(
        self,
        source: str,
        variables: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        # Import lazily so the pure adapter remains testable without Home Assistant.
        from homeassistant.helpers.template import Template

        rendered = Template(source, self._hass).async_render(
            dict(variables),
            parse_result=False,
        )
        payload = yaml.safe_load(rendered)
        if not isinstance(payload, Mapping):
            raise ValueError("GOS payload template must render to a YAML mapping")
        if not all(isinstance(key, str) for key in payload):
            raise ValueError("GOS payload keys must be strings")
        return dict(payload)


@dataclass(frozen=True, slots=True)
class GenericOutputSnapshot:
    """Last attempted GOS output without exposing user templates or payloads."""

    state: GenericOutputState = GenericOutputState.SAFE_ACTION_REQUESTED
    attempted_at: datetime | None = None
    commanded_temperature: float | None = None
    service_call_count: int = 0
    acknowledged: bool | None = None
    last_error: str | None = None


class GenericOutputError(RuntimeError):
    """Raised after a failed GOS command and best-effort safe action."""


class GenericOutput:
    """Apply supervised V3 output and actively fail to a configured safe action."""

    physical_enabled = True

    def __init__(
        self,
        *,
        config: GenericOutputConfig,
        transport: ServiceCallTransport,
        renderer: PayloadRenderer,
        feedback: OutputFeedback | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._transport = transport
        self._renderer = renderer
        self._feedback = feedback
        self._monotonic = monotonic
        self._lock = asyncio.Lock()
        self._service_call_count = 0
        self._fault_latched = False
        self._last_received_at: float | None = None
        self._last_command_at: float | None = None
        self._last_commanded_temperature: float | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._watchdog_changed = asyncio.Event()
        self._snapshot = GenericOutputSnapshot()

    @property
    def snapshot(self) -> GenericOutputSnapshot:
        """Return redacted physical-output diagnostics."""
        return self._snapshot

    async def async_initialize(self) -> None:
        """Request the configured safe state before accepting active commands."""
        await self._stop_watchdog()
        async with self._lock:
            try:
                await self._request_safe(reason="initialize", output=None)
            except Exception as err:
                self._record_fault(err)
                raise GenericOutputError(
                    self._snapshot.last_error or "GOS safe action failed"
                ) from err
            self._fault_latched = False
            self._last_received_at = None
            self._last_command_at = None
            self._last_commanded_temperature = None
            self._record_safe()
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop(),
            name="pumpsteer-gos-watchdog",
        )

    async def async_publish(self, output: SupervisedOutput) -> None:
        """Apply one supervised output or explicitly request the safe action."""
        if not isinstance(output, SupervisedOutput):
            raise TypeError("GOS accepts only SupervisedOutput")
        if not output.apply_physical:
            raise ValueError("active GOS output requires physical authorization")
        async with self._lock:
            now = self._monotonic()
            self._last_received_at = now
            self._watchdog_changed.set()
            attempted_at = output.decision.decided_at
            if self._fault_latched:
                try:
                    await self._request_safe(reason="fault_latched", output=output)
                except Exception as err:  # noqa: BLE001
                    self._record_fault(err, attempted_at=attempted_at)
                raise GenericOutputError(
                    "physical output is fault-latched; reload after correcting "
                    "the fault"
                )
            if output.fallback_active:
                try:
                    await self._request_safe(
                        reason="controller_fallback",
                        output=output,
                    )
                except Exception as err:
                    self._record_fault(err, attempted_at=attempted_at)
                    raise GenericOutputError(
                        self._snapshot.last_error or "GOS safe action failed"
                    ) from err
                self._last_command_at = None
                self._last_commanded_temperature = None
                self._record_safe(attempted_at=attempted_at)
                return

            try:
                temperature = self._safe_temperature(output.value)
                if self._interval_limited(now):
                    self._snapshot = GenericOutputSnapshot(
                        state=GenericOutputState.ACTIVE_COMMAND_INTERVAL_LIMITED,
                        attempted_at=attempted_at,
                        commanded_temperature=self._last_commanded_temperature,
                        service_call_count=self._service_call_count,
                        acknowledged=(True if self._feedback is not None else None),
                    )
                    return
                await self._call_template(
                    target=self._config.command_target,
                    template=self._config.command_payload_template,
                    variables=self._variables(
                        output=output,
                        temperature=temperature,
                        safe_reason=None,
                    ),
                )
                acknowledged: bool | None = None
                state = GenericOutputState.ACTIVE_COMMAND_SENT
                if self._feedback is not None:
                    async with asyncio.timeout(
                        self._config.feedback_timeout.total_seconds()
                    ):
                        acknowledged = await self._feedback.async_verify(temperature)
                    if acknowledged is not True:
                        raise RuntimeError(
                            "GOS output feedback did not acknowledge command"
                        )
                    state = GenericOutputState.ACTIVE_COMMAND_ACKNOWLEDGED
            except Exception as err:
                safe_error = None
                try:
                    await self._request_safe(reason="write_failure", output=output)
                except Exception as fallback_err:  # noqa: BLE001
                    safe_error = fallback_err
                message = f"{type(err).__name__}: {err}"
                if safe_error is not None:
                    message = (
                        f"{message}; safe action failed: "
                        f"{type(safe_error).__name__}: {safe_error}"
                    )
                self._fault_latched = True
                self._snapshot = GenericOutputSnapshot(
                    state=GenericOutputState.FAULT,
                    attempted_at=attempted_at,
                    service_call_count=self._service_call_count,
                    last_error=message,
                )
                raise GenericOutputError(message) from err

            self._last_command_at = now
            self._last_commanded_temperature = temperature
            self._snapshot = GenericOutputSnapshot(
                state=state,
                attempted_at=attempted_at,
                commanded_temperature=temperature,
                service_call_count=self._service_call_count,
                acknowledged=acknowledged,
            )

    async def async_shutdown(self) -> None:
        """Stop the watchdog and explicitly request the configured safe state."""
        await self._stop_watchdog()
        async with self._lock:
            try:
                await self._request_safe(reason="shutdown", output=None)
            except Exception as err:
                self._record_fault(err)
                raise GenericOutputError(
                    self._snapshot.last_error or "GOS safe action failed"
                ) from err
            self._fault_latched = False
            self._last_received_at = None
            self._last_command_at = None
            self._last_commanded_temperature = None
            self._record_safe()

    async def _watchdog_loop(self) -> None:
        timeout = self._config.watchdog_timeout.total_seconds()
        try:
            while True:
                self._watchdog_changed.clear()
                async with self._lock:
                    received_at = self._last_received_at
                    active = (
                        self._last_command_at is not None and not self._fault_latched
                    )
                if not active or received_at is None:
                    await self._watchdog_changed.wait()
                    continue
                remaining = max(0.0, timeout - (self._monotonic() - received_at))
                try:
                    await asyncio.wait_for(
                        self._watchdog_changed.wait(),
                        timeout=remaining,
                    )
                    continue
                except TimeoutError:
                    pass
                async with self._lock:
                    received_at = self._last_received_at
                    if (
                        self._fault_latched
                        or self._last_command_at is None
                        or received_at is None
                        or self._monotonic() - received_at < timeout
                    ):
                        continue
                    try:
                        await self._request_safe(reason="watchdog_timeout", output=None)
                    except Exception as err:  # noqa: BLE001
                        self._record_fault(err)
                    else:
                        self._fault_latched = True
                        self._last_command_at = None
                        self._last_commanded_temperature = None
                        self._snapshot = GenericOutputSnapshot(
                            state=GenericOutputState.FAULT,
                            service_call_count=self._service_call_count,
                            last_error=(
                                "GOS watchdog expired; safe action was requested"
                            ),
                        )
        except asyncio.CancelledError:
            raise

    async def _stop_watchdog(self) -> None:
        task = self._watchdog_task
        self._watchdog_task = None
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _request_safe(
        self,
        *,
        reason: str,
        output: SupervisedOutput | None,
    ) -> None:
        temperature = None
        if output is not None and output.fallback_active:
            try:
                temperature = self._safe_temperature(output.value)
            except (TypeError, ValueError):
                # Never interpolate an untrusted command into the safe action.
                temperature = None
        await self._call_template(
            target=self._config.safe_target,
            template=self._config.safe_payload_template,
            variables=self._variables(
                output=output,
                temperature=temperature,
                safe_reason=reason,
            ),
        )

    async def _call_template(
        self,
        *,
        target: tuple[str, str],
        template: str,
        variables: Mapping[str, Any],
    ) -> None:
        payload = self._renderer.render(template, variables)
        async with asyncio.timeout(self._config.service_call_timeout.total_seconds()):
            await self._transport.async_call(target[0], target[1], payload)
        self._service_call_count += 1

    def _interval_limited(self, now: float) -> bool:
        if self._last_command_at is None:
            return False
        return now - self._last_command_at < (
            self._config.minimum_write_interval.total_seconds()
        )

    def _safe_temperature(self, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("virtual temperature must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("virtual temperature must be finite")
        if not (
            self._config.minimum_temperature
            <= numeric
            <= self._config.maximum_temperature
        ):
            raise ValueError("virtual temperature is outside the GOS safety range")
        rounded = (
            round(numeric / self._config.rounding_step) * self._config.rounding_step
        )
        return min(
            self._config.maximum_temperature,
            max(self._config.minimum_temperature, rounded),
        )

    def _variables(
        self,
        *,
        output: SupervisedOutput | None,
        temperature: float | None,
        safe_reason: str | None,
    ) -> dict[str, Any]:
        return {
            "fake_temp": temperature,
            "virtual_temperature": temperature,
            "fallback_active": bool(output and output.fallback_active),
            "control_state": output.decision.state.value if output else None,
            "reason_codes": (
                [reason.value for reason in output.decision.reason_codes]
                if output
                else []
            ),
            "safe_reason": safe_reason,
        }

    def _record_safe(self, *, attempted_at: datetime | None = None) -> None:
        self._snapshot = GenericOutputSnapshot(
            state=GenericOutputState.SAFE_ACTION_REQUESTED,
            attempted_at=attempted_at,
            service_call_count=self._service_call_count,
        )

    def _record_fault(
        self,
        err: Exception,
        *,
        attempted_at: datetime | None = None,
    ) -> None:
        self._fault_latched = True
        self._snapshot = GenericOutputSnapshot(
            state=GenericOutputState.FAULT,
            attempted_at=attempted_at,
            service_call_count=self._service_call_count,
            last_error=f"{type(err).__name__}: {err}",
        )
