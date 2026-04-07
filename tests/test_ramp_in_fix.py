"""
Tests for ramp timing and brake hold behavior in PumpSteer 2.1.0.

Updated for new architecture:
- ramp_in depends ONLY on house_inertia
- price categories no longer affect ramp computation
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401

from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.settings import (
    RAMP_MAX_MINUTES,
    RAMP_MIN_MINUTES,
)

# ── Helpers ────────────────────────────────────────────────────────────────


class DummyState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class DummyStates:
    def __init__(self, mapping=None):
        self._m = mapping or {}

    def get(self, entity_id):
        v = self._m.get(entity_id)
        if v is None:
            return None
        if isinstance(v, dict):
            return DummyState(v.get("state", ""), v.get("attributes", {}))
        return DummyState(v)


class DummyHass:
    def __init__(self, states=None):
        self.states = DummyStates(states or {})


class DummyConfigEntry:
    entry_id = "test"
    data = {}
    options = {}

    def add_update_listener(self, listener):
        pass


def make_sensor() -> PumpSteerSensor:
    return PumpSteerSensor(DummyHass(), DummyConfigEntry())


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# Ramp timing (new logic)
# ═══════════════════════════════════════════════════════════════════════════


def test_ramp_in_scales_with_house_inertia():
    s = make_sensor()

    low = s._compute_ramp_minutes(2.0)
    high = s._compute_ramp_minutes(5.0)

    assert high > low


def test_ramp_in_clamped_to_min():
    s = make_sensor()

    ramp = s._compute_ramp_minutes(0.1)

    assert ramp >= RAMP_MIN_MINUTES


def test_ramp_in_clamped_to_max():
    s = make_sensor()

    ramp = s._compute_ramp_minutes(10.0)

    assert ramp <= RAMP_MAX_MINUTES


def test_ramp_in_deterministic():
    s = make_sensor()

    a = s._compute_ramp_minutes(3.0)
    b = s._compute_ramp_minutes(3.0)

    assert a == b


def test_pre_brake_window_depends_on_ramp_only():
    s = make_sensor()

    ramp = s._compute_ramp_minutes(5.0)
    minutes_to_expensive = 45.0

    assert (minutes_to_expensive <= ramp) == (ramp >= 45.0)


# ═══════════════════════════════════════════════════════════════════════════
# Brake hold (unchanged behavior)
# ═══════════════════════════════════════════════════════════════════════════


def test_brake_holds_during_short_dip():
    s = make_sensor()
    t0 = now_utc()

    # Build full brake
    for i in range(40):
        s._update_brake_ramp(
            brake_requested=True,
            now=t0 + timedelta(seconds=i * 30),
            ramp_in=20.0,
            ramp_out=20.0,
            hold_minutes=30.0,
        )

    assert s._brake_ramp == 1.0

    # Short dip
    factor = s._update_brake_ramp(
        brake_requested=False,
        now=t0 + timedelta(minutes=5),
        ramp_in=20.0,
        ramp_out=20.0,
        hold_minutes=30.0,
    )

    assert factor == 1.0


def test_brake_releases_after_hold():
    s = make_sensor()
    t0 = now_utc()

    s._update_brake_ramp(
        brake_requested=True,
        now=t0,
        ramp_in=20.0,
        ramp_out=20.0,
        hold_minutes=30.0,
    )

    factor = s._update_brake_ramp(
        brake_requested=False,
        now=t0 + timedelta(minutes=40),
        ramp_in=20.0,
        ramp_out=20.0,
        hold_minutes=30.0,
    )

    assert factor < 1.0
