"""Sensor exposing PumpSteer's estimated load-shifting value.

Observational only: it receives samples from the controller via the
dispatcher and never feeds anything back into control decisions.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .savings import SavingsEstimator, SavingsSample, savings_signal
from .utils import safe_float

_LOGGER = logging.getLogger(__name__)


class PumpSteerSavingsSensor(SensorEntity, RestoreEntity):
    """Accumulated estimated value of shifted heating energy."""

    _attr_has_entity_name = True
    _attr_name = "Estimated Savings"
    _attr_icon = "mdi:piggy-bank-outline"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry_id: str, device_info) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._estimator = SavingsEstimator()
        self._last_kwh_per_c_hour: float | None = None
        self._attr_unique_id = f"{entry_id}_estimated_savings"
        self._attr_device_info = device_info
        # Signed running total: TOTAL (not TOTAL_INCREASING) so a negative
        # hour is not mistaken for a meter reset by long-term statistics.
        self._attr_state_class = "total"
        currency = getattr(getattr(hass, "config", None), "currency", None)
        if isinstance(currency, str) and len(currency) == 3:
            self._attr_device_class = "monetary"
            self._attr_native_unit_of_measurement = currency
        else:
            self._attr_native_unit_of_measurement = None

    @property
    def native_value(self) -> float:
        return round(self._estimator.total, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "reduced_kwh": round(self._estimator.reduced_kwh, 3),
            "added_kwh": round(self._estimator.added_kwh, 3),
            "kwh_per_c_hour": self._last_kwh_per_c_hour,
            "method": "shifted_kwh_x_price_minus_daily_mean",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            restored = safe_float(last.state)
            if restored is not None:
                self._estimator.total = restored
            self._estimator.reduced_kwh = (
                safe_float(last.attributes.get("reduced_kwh")) or 0.0
            )
            self._estimator.added_kwh = (
                safe_float(last.attributes.get("added_kwh")) or 0.0
            )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, savings_signal(self._entry_id), self._handle_sample
            )
        )

    @callback
    def _handle_sample(self, sample: SavingsSample) -> None:
        try:
            self._last_kwh_per_c_hour = sample.kwh_per_c_hour
            self._estimator.update(sample)
        except Exception as err:  # never let diagnostics disturb anything
            _LOGGER.debug("Savings sample ignored: %s", err)
            return
        self.async_write_ha_state()
