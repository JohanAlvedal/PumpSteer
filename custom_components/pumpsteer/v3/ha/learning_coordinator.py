"""Home Assistant timer lifecycle for observation-only learning."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

if TYPE_CHECKING:
    from .learning_runtime import ObservationLearningRuntime

_LOGGER = logging.getLogger(__name__)


class ObservationLearningCoordinator:
    """Own one bounded timer and collection task for a learning runtime."""

    def __init__(
        self,
        hass: HomeAssistant,
        runtime: ObservationLearningRuntime,
    ) -> None:
        self._hass = hass
        self._runtime = runtime
        self._cancel_timer: Any | None = None
        self._active_task: asyncio.Task[Any] | None = None
        self._started = False
        self._stopped = False

    @property
    def runtime(self) -> ObservationLearningRuntime:
        """Return the entry-owned observation runtime."""
        return self._runtime

    @callback
    def start(self) -> None:
        """Start periodic collection without performing an immediate query."""
        if self._started:
            return
        if self._stopped:
            return
        self._cancel_timer = async_track_time_interval(
            self._hass,
            self._interval_elapsed,
            self._runtime.config.collection_interval,
        )
        self._started = True

    @callback
    def stop(self) -> None:
        """Synchronously release all entry-owned learning resources."""
        if self._stopped:
            return
        self._stopped = True
        cancel_timer = self._cancel_timer
        self._cancel_timer = None
        if cancel_timer is not None:
            cancel_timer()
        task = self._active_task
        if task is not None and not task.done():
            task.cancel()
        self._runtime.stop()

    async def async_shutdown(self) -> None:
        """Stop and drain active Recorder or checkpoint work before reload."""
        task = self._active_task
        self.stop()
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                _LOGGER.exception(
                    "Observation learning shutdown completed with an error"
                )
        await self._runtime.async_shutdown()

    @callback
    def _interval_elapsed(self, now: datetime) -> None:
        """Start at most one HA-tracked collection task per interval."""
        if self._stopped:
            return
        task = self._active_task
        if task is not None and not task.done():
            return
        now_utc = _as_utc(now)
        task = self._hass.async_create_task(
            self._runtime.async_collect(now_utc=now_utc)
        )
        self._active_task = task
        task.add_done_callback(self._collection_done)

    @callback
    def _collection_done(self, task: asyncio.Task[Any]) -> None:
        """Consume task completion so failures never become orphaned."""
        if self._active_task is task:
            self._active_task = None
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            _LOGGER.exception("Unexpected observation learning task failure")


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timer timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timer timestamp must be timezone-aware")
    return value.astimezone(UTC)
