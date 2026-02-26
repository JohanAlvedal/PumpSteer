"""Reusable brake ramp controller state machine for PumpSteer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BrakePhase(str, Enum):
    """State machine phases for brake ramping."""

    IDLE = "idle"
    RAMPING_UP = "ramping_up"
    HOLDING = "holding"
    RAMPING_DOWN = "ramping_down"


@dataclass(frozen=True)
class BrakeRampResult:
    """Result of one ramp controller update tick."""

    offset_c: float
    phase: str
    reason_code: str
    target_offset_c: float
    seconds_in_phase: int


@dataclass
class BrakeRampSnapshot:
    """Serializable snapshot used for persistence."""

    phase: str
    offset_c: float
    target_offset_c: float
    last_phase_change_ts: Optional[float]
    hold_started_ts: Optional[float]


class BrakeRampController:
    """Generic state machine that ramps brake offset up/down without overshoot."""

    def __init__(
        self,
        initial_phase: str = BrakePhase.IDLE.value,
        initial_offset_c: float = 0.0,
        initial_target_offset_c: float = 0.0,
        last_phase_change_ts: Optional[float] = None,
        hold_started_ts: Optional[float] = None,
    ) -> None:
        self._phase = self._parse_phase(initial_phase)
        self._offset_c = max(0.0, float(initial_offset_c))
        self._target_offset_c = max(0.0, float(initial_target_offset_c))
        self._last_phase_change_ts = last_phase_change_ts
        self._hold_started_ts = hold_started_ts

    @property
    def phase(self) -> str:
        return self._phase.value

    @property
    def offset_c(self) -> float:
        return self._offset_c

    @property
    def target_offset_c(self) -> float:
        return self._target_offset_c

    @property
    def last_phase_change_ts(self) -> Optional[float]:
        return self._last_phase_change_ts

    def update(
        self,
        now_ts: float,
        brake_request: bool,
        near_brake: bool = False,
        hold_offset_c: float = 6.0,
        max_delta_per_step_c: float = 0.20,
        min_hold_s: Optional[int] = None,
        force_release: bool = False,
    ) -> BrakeRampResult:
        """Advance one control tick and return the current brake state."""
        hold_offset_c = max(0.0, float(hold_offset_c))
        step_c = max(0.0, float(max_delta_per_step_c))
        min_hold_s = max(0, int(min_hold_s)) if min_hold_s is not None else None

        self._target_offset_c = hold_offset_c if (brake_request or near_brake) else 0.0

        if brake_request and self._phase in (BrakePhase.IDLE, BrakePhase.RAMPING_DOWN):
            self._set_phase(BrakePhase.RAMPING_UP, now_ts)
        elif not brake_request and not near_brake and force_release:
            self._set_phase(BrakePhase.RAMPING_DOWN, now_ts)

        if not brake_request and not near_brake and self._phase in (
            BrakePhase.RAMPING_UP,
            BrakePhase.HOLDING,
        ):
            if self._can_release(now_ts, min_hold_s, force_release):
                self._set_phase(BrakePhase.RAMPING_DOWN, now_ts)

        if self._phase == BrakePhase.RAMPING_UP:
            self._offset_c = min(self._target_offset_c, self._offset_c + step_c)
            if self._offset_c >= self._target_offset_c:
                self._offset_c = self._target_offset_c
                self._set_phase(BrakePhase.HOLDING, now_ts)
                if self._hold_started_ts is None:
                    self._hold_started_ts = now_ts

        elif self._phase == BrakePhase.HOLDING:
            self._offset_c = self._target_offset_c
            if self._hold_started_ts is None:
                self._hold_started_ts = now_ts

        elif self._phase == BrakePhase.RAMPING_DOWN:
            self._offset_c = max(0.0, self._offset_c - step_c)
            if self._offset_c <= 0.0:
                self._offset_c = 0.0
                self._set_phase(BrakePhase.IDLE, now_ts)

        else:
            self._offset_c = 0.0

        reason_code = self._reason_code(brake_request, near_brake)
        seconds_in_phase = self._seconds_in_phase(now_ts)

        return BrakeRampResult(
            offset_c=round(self._offset_c, 4),
            phase=self._phase.value,
            reason_code=reason_code,
            target_offset_c=round(self._target_offset_c, 4),
            seconds_in_phase=seconds_in_phase,
        )

    def snapshot(self) -> BrakeRampSnapshot:
        """Return a snapshot that can be persisted between reloads."""
        return BrakeRampSnapshot(
            phase=self._phase.value,
            offset_c=self._offset_c,
            target_offset_c=self._target_offset_c,
            last_phase_change_ts=self._last_phase_change_ts,
            hold_started_ts=self._hold_started_ts,
        )

    def _can_release(
        self,
        now_ts: float,
        min_hold_s: Optional[int],
        force_release: bool,
    ) -> bool:
        if force_release:
            return True
        if min_hold_s is None or min_hold_s <= 0:
            return True
        if self._phase != BrakePhase.HOLDING:
            return True
        if self._hold_started_ts is None:
            return True
        return (now_ts - self._hold_started_ts) >= min_hold_s

    def _reason_code(self, brake_request: bool, near_brake: bool) -> str:
        if self._phase == BrakePhase.IDLE:
            return "BRAKE_IDLE"
        if self._phase == BrakePhase.RAMPING_DOWN:
            return "BRAKE_RAMP_DOWN"
        if self._phase == BrakePhase.RAMPING_UP:
            return "BRAKE_RAMP_UP"
        if near_brake and not brake_request:
            return "BRAKE_BRIDGE_HOLD"
        return "BRAKE_HOLD"

    def _seconds_in_phase(self, now_ts: float) -> int:
        if self._last_phase_change_ts is None:
            return 0
        return max(0, int(now_ts - self._last_phase_change_ts))

    def _set_phase(self, phase: BrakePhase, now_ts: float) -> None:
        if self._phase == phase:
            return
        self._phase = phase
        self._last_phase_change_ts = now_ts
        if phase != BrakePhase.HOLDING:
            self._hold_started_ts = None

    def _parse_phase(self, phase: str) -> BrakePhase:
        try:
            return BrakePhase(phase)
        except ValueError:
            return BrakePhase.IDLE
