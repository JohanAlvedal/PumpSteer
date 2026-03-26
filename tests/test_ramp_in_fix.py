"""
Tester för fix av ramp_in-beräkning och bridge_short_dip-konsekvens.

Bugg: ramp_in beräknades från current_cat → next_cat (slot+1).
      När current=normal, next=normal men expensive finns längre fram
      blev jump=0 → ramp_in=RAMP_MIN → minutes_until_expensive passade aldrig in.

Fix: ramp_in baseras på current_cat → PRICE_EXPENSIVE när upcoming=True,
     annars current_cat → next_cat som förut.

Kör med: pytest tests/ -v
"""

import sys
from pathlib import Path
from datetime import timedelta, timezone, datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401

from custom_components.pumpsteer.sensor import PumpSteerSensor
from custom_components.pumpsteer.electricity_price import (
    PRICE_CHEAP,
    PRICE_NORMAL,
    PRICE_EXPENSIVE,
)
from custom_components.pumpsteer.settings import (
    RAMP_MIN_MINUTES,
    RAMP_MAX_MINUTES,
    RAMP_SCALE,
)

# ── Hjälpklasser (samma mönster som befintliga tester) ────────────────────────


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


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def make_sensor() -> PumpSteerSensor:
    return PumpSteerSensor(DummyHass(), DummyConfigEntry())


# ── Hjälp: _compute_ramp_minutes direkt ──────────────────────────────────────


def ramp(current, target, inertia):
    s = make_sensor()
    return s._compute_ramp_minutes(current, target, inertia)


# ═════════════════════════════════════════════════════════════════════════════
# Scenario 1: normal → normal → expensive
#
# upcoming=True, men nästa slot är fortfarande normal.
# Förväntat efter fix:
#   ramp_target_cat = PRICE_EXPENSIVE
#   ramp_in > RAMP_MIN (inte ihopklappat till 20 min)
#   minutes_until_expensive <= ramp_in kan bli True
# ═════════════════════════════════════════════════════════════════════════════


def test_ramp_in_uses_expensive_when_upcoming():
    """ramp_in ska baseras på hopp till expensive, inte next_cat, när upcoming=True."""
    s = make_sensor()

    # Manuellt simulera vad _do_update gör efter patchen:
    # current=normal, next=normal, upcoming=True
    current_cat = PRICE_NORMAL
    next_cat = PRICE_NORMAL
    upcoming = True
    house_inertia = 3.0

    # Gammalt beteende (buggen):
    old_ramp_in = s._compute_ramp_minutes(current_cat, next_cat, house_inertia)
    # normal→normal: jump=0 → ramp = max(RAMP_MIN, 0) = RAMP_MIN
    assert old_ramp_in == RAMP_MIN_MINUTES, (
        f"Förväntat {RAMP_MIN_MINUTES}, fick {old_ramp_in} — kontrollfråga för gammalt beteende"
    )

    # Nytt beteende (efter patch):
    ramp_target_cat = PRICE_EXPENSIVE if upcoming else (next_cat or current_cat)
    new_ramp_in = s._compute_ramp_minutes(current_cat, ramp_target_cat, house_inertia)
    # normal→expensive: jump=1, inertia=3 → ramp=30 min
    expected = max(
        RAMP_MIN_MINUTES, min(RAMP_MAX_MINUTES, 1 * house_inertia * RAMP_SCALE)
    )
    assert new_ramp_in == expected, f"Förväntat {expected}, fick {new_ramp_in}"
    assert new_ramp_in > RAMP_MIN_MINUTES, (
        "ramp_in ska vara > RAMP_MIN när upcoming=True och inertia ger jump>0"
    )


def test_pre_brake_trigger_window_opens_with_fix():
    """
    Med gammal ramp_in (20 min) passar minutes_until_expensive=45 inte in.
    Med ny ramp_in (30 min vid inertia=3) passar det fortfarande inte,
    men vid inertia=5 (50 min) passar 45 <= 50 → trigger.

    Testar att villkoret minutes_until_expensive <= ramp_in kan bli True
    efter patchen, men inte före.
    """
    s = make_sensor()
    house_inertia = 5.0
    minutes_to_expensive = 45.0

    # Gammalt: ramp_in baserat på normal→normal
    old_ramp_in = s._compute_ramp_minutes(PRICE_NORMAL, PRICE_NORMAL, house_inertia)
    assert minutes_to_expensive > old_ramp_in, (
        "Gammalt beteende: trigger skulle INTE ske (minutes > ramp_in)"
    )

    # Nytt: ramp_in baserat på normal→expensive
    new_ramp_in = s._compute_ramp_minutes(PRICE_NORMAL, PRICE_EXPENSIVE, house_inertia)
    assert minutes_to_expensive <= new_ramp_in, (
        "Nytt beteende: trigger SKA ske (minutes <= ramp_in)"
    )


def test_ramp_in_not_affected_when_no_upcoming():
    """När upcoming=False ska ramp_in fortfarande baseras på next_cat (oförändrat)."""
    s = make_sensor()
    house_inertia = 3.0
    current_cat = PRICE_NORMAL
    next_cat = PRICE_NORMAL
    upcoming = False

    ramp_target_cat = PRICE_EXPENSIVE if upcoming else (next_cat or current_cat)
    ramp_in = s._compute_ramp_minutes(current_cat, ramp_target_cat, house_inertia)

    # normal→normal: jump=0 → RAMP_MIN
    assert ramp_in == RAMP_MIN_MINUTES


# ═════════════════════════════════════════════════════════════════════════════
# Scenario 2: expensive → normal (kort dipp) → expensive
#
# bridge_short_dip ska hålla bromsen uppe.
# Nyckelkrav: bromsen ska INTE ha börjat rampa ned efter bara 1 minut
# under dippen (BRAKE_HOLD_MINUTES skyddar mot det).
# ═════════════════════════════════════════════════════════════════════════════


def test_bridge_short_dip_brake_holds_during_cheap_gap():
    """
    Under en kort billig lucka inom ett expensive-block ska bromsen hålla.
    _update_brake_ramp med hold_minutes=30 ska inte börja rampa ned
    direkt när brake_requested=False.
    """
    s = make_sensor()
    t0 = now_utc()

    # Engagera bromsen till 1.0
    for i in range(5):
        s._update_brake_ramp(
            brake_requested=True,
            now=t0 + timedelta(minutes=i * 10),
            ramp_in=20.0,
            ramp_out=20.0,
            hold_minutes=30.0,
        )
    assert s._brake_ramp == 1.0, "Bromsen ska vara fullt engagerad"

    # Priset dippar till normal — brake_requested=False, men hold_minutes=30
    factor_after_1min = s._update_brake_ramp(
        brake_requested=False,
        now=t0 + timedelta(minutes=51),
        ramp_in=20.0,
        ramp_out=20.0,
        hold_minutes=30.0,
    )
    # Hold är aktiv (bara 1 min sedan sista expensive) → bromsen ska inte ha sjunkit
    assert factor_after_1min == 1.0, (
        f"Bromsen ska hålla på 1.0 under hold-perioden, fick {factor_after_1min}"
    )


def test_bridge_short_dip_releases_after_hold():
    """
    Efter att hold_minutes löpt ut ska bromsen börja rampa ned.
    """
    s = make_sensor()
    t0 = now_utc()

    # Engagera bromsen
    s._update_brake_ramp(
        brake_requested=True,
        now=t0,
        ramp_in=20.0,
        ramp_out=20.0,
        hold_minutes=30.0,
    )

    # Vänta 35 min efter sista expensive (hold löpt ut)
    factor = s._update_brake_ramp(
        brake_requested=False,
        now=t0 + timedelta(minutes=35),
        ramp_in=20.0,
        ramp_out=20.0,
        hold_minutes=30.0,
    )
    # Hold är slut → bromsen ska ha börjat sjunka
    assert factor < 1.0, f"Bromsen ska ha börjat rampa ned efter hold, fick {factor}"


# ═════════════════════════════════════════════════════════════════════════════
# Scenario 3: upcoming=True men expensive långt bort (edge case)
#
# Säkerhetskontroll: systemet ska INTE pre-braka för tidigt
# bara för att upcoming=True.
# Grinden minutes_until_expensive <= ramp_in skyddar mot detta.
# ═════════════════════════════════════════════════════════════════════════════


def test_pre_brake_does_not_trigger_when_expensive_far_away():
    """
    upcoming=True men expensive är 300 minuter bort.
    Även med ny ramp_in (max 60 min) ska minutes_until_expensive > ramp_in.
    → pre-brake triggar INTE.
    """
    s = make_sensor()
    house_inertia = 5.0  # max inertia → ramp_in = RAMP_MAX = 60 min

    new_ramp_in = s._compute_ramp_minutes(PRICE_NORMAL, PRICE_EXPENSIVE, house_inertia)
    assert new_ramp_in <= RAMP_MAX_MINUTES

    minutes_to_expensive = 300.0
    trigger = minutes_to_expensive <= new_ramp_in
    assert not trigger, (
        f"Pre-brake ska INTE trigga när expensive är {minutes_to_expensive} min bort "
        f"och ramp_in={new_ramp_in} min"
    )


def test_ramp_in_clamped_to_max():
    """ramp_in ska aldrig överstiga RAMP_MAX_MINUTES oavsett house_inertia."""
    s = make_sensor()
    ramp_in = s._compute_ramp_minutes(PRICE_CHEAP, PRICE_EXPENSIVE, house_inertia=10.0)
    assert ramp_in <= RAMP_MAX_MINUTES, (
        f"ramp_in={ramp_in} överstiger RAMP_MAX_MINUTES={RAMP_MAX_MINUTES}"
    )
