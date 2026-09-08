"""Home Assistant storage boundary for observation-only learning checkpoints."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..learning.checkpoint_codec import (
    decode_learning_checkpoint,
    encode_learning_checkpoint,
)

if TYPE_CHECKING:
    from ..learning.checkpoint import LearningCheckpoint


_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "pumpsteer.v3.observation_learning"


class LearningStoreWriteError(RuntimeError):
    """Raised when a complete checkpoint cannot be read back after saving."""


class HomeAssistantLearningStore:
    """Persist one config entry's learning checkpoint through HA Store."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise ValueError("entry_id must be a non-empty string")
        self._store: Store[dict[str, Any]] = Store(
            hass,
            version=STORAGE_VERSION,
            key=f"{STORAGE_KEY_PREFIX}.{entry_id}",
            private=True,
            atomic_writes=True,
            serialize_in_event_loop=True,
        )

    async def async_load(
        self,
        *,
        expected_entry_id: str,
        expected_indoor_entity: str,
        expected_outdoor_entity: str,
        not_after: datetime,
    ) -> LearningCheckpoint | None:
        """Load and validate a complete checkpoint, if one exists."""
        encoded = await self._store.async_load()
        if encoded is None:
            return None

        source_identity = encoded.get("source_identity")
        stored_indoor = None
        stored_outdoor = None
        if isinstance(source_identity, Mapping):
            stored_indoor = source_identity.get("indoor_entity_id")
            stored_outdoor = source_identity.get("outdoor_entity_id")

        checkpoint = decode_learning_checkpoint(
            encoded,
            expected_entry_id=expected_entry_id,
            expected_indoor_entity_id=stored_indoor,
            expected_outdoor_entity_id=stored_outdoor,
            not_after=not_after,
        )
        if (
            checkpoint.indoor_entity_id != expected_indoor_entity
            or checkpoint.outdoor_entity_id != expected_outdoor_entity
        ):
            _LOGGER.info(
                "Ignoring observation-learning checkpoint because configured sensor sources changed"
            )
            return None
        return checkpoint

    async def async_save(self, checkpoint: LearningCheckpoint) -> None:
        """Save and read-verify one complete immutable checkpoint."""
        encoded = encode_learning_checkpoint(checkpoint)
        write = asyncio.create_task(self._async_save_and_verify(encoded))
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            # HA Store may already have handed an atomic write to an executor.
            # Drain it before unload/reload can create a newer runtime.
            await write
            raise
        except Exception as err:
            raise LearningStoreWriteError(
                "learning checkpoint write verification failed"
            ) from err

    async def _async_save_and_verify(self, encoded: dict[str, Any]) -> None:
        """Complete one atomic write and verify its exact stored representation."""
        await self._store.async_save(encoded)
        verified = await self._store.async_load()
        if verified != encoded:
            raise LearningStoreWriteError(
                "learning checkpoint write verification failed"
            )


__all__ = [
    "STORAGE_KEY_PREFIX",
    "STORAGE_VERSION",
    "HomeAssistantLearningStore",
    "LearningStoreWriteError",
]
