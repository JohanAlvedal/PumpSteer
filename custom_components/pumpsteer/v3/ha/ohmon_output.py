"""Fail-to-bypass MQTT output adapter for OhmOnWiFi devices."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from homeassistant.core import HomeAssistant

from ..control.supervisor import SupervisedOutput


class OhmonOutputState(StrEnum):
    """Physical adapter state, separate from the controller mode."""

    BYPASS_REQUESTED = "bypass_requested"
    ACTIVE_COMMAND_SENT = "active_command_sent"
    FAULT = "fault"


@dataclass(frozen=True, slots=True)
class OhmonMqttConfig:
    """Validated MQTT contract for one OhmOnWiFi/Plus device."""

    base_topic: str
    watchdog_confirmed: bool
    minimum_temperature: float = -30.0
    maximum_temperature: float = 30.0
    rounding_step: float = 0.5

    def __post_init__(self) -> None:
        if not isinstance(self.base_topic, str):
            raise TypeError("base_topic must be a string")
        topic = self.base_topic.strip()
        if (
            not topic
            or not topic.endswith("/")
            or "+" in topic
            or "#" in topic
            or any(character.isspace() for character in topic)
        ):
            raise ValueError("base_topic must be a concrete MQTT prefix ending with /")
        object.__setattr__(self, "base_topic", topic)
        if self.watchdog_confirmed is not True:
            raise ValueError("the Ohmon watchdog must be explicitly confirmed")
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

    @property
    def temperature_set_topic(self) -> str:
        return f"{self.base_topic}temperature/set"

    @property
    def relay_set_topic(self) -> str:
        return f"{self.base_topic}relay/set"


class MqttPublishTransport(Protocol):
    """Minimal broker boundary used by the device adapter."""

    async def async_publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        """Publish one message or raise if broker delivery fails."""


class HomeAssistantMqttTransport:
    """Publish through Home Assistant's configured local MQTT integration."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def async_publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        has_service = getattr(self._hass.services, "has_service", None)
        if has_service is not None and not has_service("mqtt", "publish"):
            raise RuntimeError("Home Assistant MQTT publish action is unavailable")
        async with asyncio.timeout(10):
            await self._hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": topic,
                    "payload": payload,
                    "qos": qos,
                    "retain": retain,
                },
                blocking=True,
            )


@dataclass(frozen=True, slots=True)
class OhmonOutputSnapshot:
    """Last attempted physical output without credentials or broker details."""

    state: OhmonOutputState = OhmonOutputState.BYPASS_REQUESTED
    attempted_at: datetime | None = None
    commanded_temperature: float | None = None
    publish_count: int = 0
    last_error: str | None = None


class OhmonOutputError(RuntimeError):
    """Raised after a failed command and best-effort bypass attempt."""


class OhmonMqttOutput:
    """Apply supervised V3 output and actively bypass on every failure path."""

    physical_enabled = True

    def __init__(
        self,
        *,
        config: OhmonMqttConfig,
        transport: MqttPublishTransport,
    ) -> None:
        self._config = config
        self._transport = transport
        self._lock = asyncio.Lock()
        self._publish_count = 0
        self._fault_latched = False
        self._snapshot = OhmonOutputSnapshot()

    @property
    def snapshot(self) -> OhmonOutputSnapshot:
        return self._snapshot

    async def async_initialize(self) -> None:
        """Start from physical-sensor bypass before control is evaluated."""
        async with self._lock:
            try:
                await self._publish_relay(False)
            except Exception as err:
                self._record_fault(err)
                raise OhmonOutputError(
                    self._snapshot.last_error or "bypass failed"
                ) from err
            self._record_bypass()
            self._fault_latched = False

    async def async_publish(self, output: SupervisedOutput) -> None:
        """Publish temperature before earning ACTIVE with a watchdog refresh."""
        if not output.apply_physical:
            raise ValueError("active Ohmon output requires physical authorization")
        async with self._lock:
            attempted_at = output.decision.decided_at
            if self._fault_latched:
                try:
                    await self._publish_relay(False)
                except Exception as err:  # noqa: BLE001
                    # The transport boundary may raise implementation-specific errors.
                    self._record_fault(err, attempted_at=attempted_at)
                raise OhmonOutputError(
                    "physical output is fault-latched; reload after correcting the fault"
                )
            if output.fallback_active:
                try:
                    await self._publish_relay(False)
                except Exception as err:
                    self._record_fault(err, attempted_at=attempted_at)
                    raise OhmonOutputError(
                        self._snapshot.last_error or "bypass failed"
                    ) from err
                self._record_bypass(attempted_at=attempted_at)
                return
            try:
                temperature = self._safe_temperature(output.value)
                await self._publish(
                    self._config.temperature_set_topic,
                    f"{temperature:.2f}",
                )
                await self._publish_relay(True)
            except Exception as err:
                bypass_error = None
                try:
                    await self._publish_relay(False)
                except Exception as fallback_err:  # noqa: BLE001
                    # The transport boundary may raise implementation-specific errors.
                    bypass_error = fallback_err
                message = f"{type(err).__name__}: {err}"
                if bypass_error is not None:
                    message = (
                        f"{message}; bypass failed: "
                        f"{type(bypass_error).__name__}: {bypass_error}"
                    )
                self._fault_latched = True
                self._snapshot = OhmonOutputSnapshot(
                    state=OhmonOutputState.FAULT,
                    attempted_at=attempted_at,
                    publish_count=self._publish_count,
                    last_error=message,
                )
                raise OhmonOutputError(message) from err
            self._snapshot = OhmonOutputSnapshot(
                state=OhmonOutputState.ACTIVE_COMMAND_SENT,
                attempted_at=attempted_at,
                commanded_temperature=temperature,
                publish_count=self._publish_count,
            )

    async def async_shutdown(self) -> None:
        """Explicitly return the relay to the physical outdoor sensor."""
        async with self._lock:
            try:
                await self._publish_relay(False)
            except Exception as err:
                self._record_fault(err)
                raise OhmonOutputError(
                    self._snapshot.last_error or "bypass failed"
                ) from err
            self._record_bypass()
            self._fault_latched = False

    async def _publish_relay(self, enabled: bool) -> None:
        await self._publish(
            self._config.relay_set_topic,
            "ON" if enabled else "OFF",
        )

    async def _publish(self, topic: str, payload: str) -> None:
        await self._transport.async_publish(
            topic,
            payload,
            qos=1,
            retain=False,
        )
        self._publish_count += 1

    def _record_bypass(self, *, attempted_at: datetime | None = None) -> None:
        self._snapshot = OhmonOutputSnapshot(
            state=OhmonOutputState.BYPASS_REQUESTED,
            attempted_at=attempted_at,
            publish_count=self._publish_count,
        )

    def _record_fault(
        self,
        err: Exception,
        *,
        attempted_at: datetime | None = None,
    ) -> None:
        self._fault_latched = True
        self._snapshot = OhmonOutputSnapshot(
            state=OhmonOutputState.FAULT,
            attempted_at=attempted_at,
            publish_count=self._publish_count,
            last_error=f"{type(err).__name__}: {err}",
        )

    def _safe_temperature(self, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("virtual temperature must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("virtual temperature must be finite")
        if (
            not self._config.minimum_temperature
            <= numeric
            <= self._config.maximum_temperature
        ):
            raise ValueError("virtual temperature is outside the Ohmon safety range")
        rounded = (
            round(numeric / self._config.rounding_step) * self._config.rounding_step
        )
        return min(
            self._config.maximum_temperature,
            max(self._config.minimum_temperature, rounded),
        )
