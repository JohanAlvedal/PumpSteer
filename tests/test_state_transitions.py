import pytest

PRICE_CHEAP = "cheap"
PRICE_NORMAL = "normal"
PRICE_EXPENSIVE = "expensive"


def simulate_brake_states(categories, bridge_max_slots=2):
    """
    Enkel testsimulator för önskat beteende:
    - börja bromsa ett steg innan expensive
    - håll bromsen under expensive
    - håll kvar bromsen över kort cheap/normal dipp
    - släpp bromsen först när billig period är tillräckligt lång
    """
    states = []
    brake_active = False

    for i, current in enumerate(categories):
        next_cat = categories[i + 1] if i + 1 < len(categories) else None

        # Aktiv dyrperiod
        if current == PRICE_EXPENSIVE:
            brake_active = True
            states.append("PRICE_BRAKE")
            continue

        # Kort dipp mellan dyra block -> håll kvar om bromsen redan är aktiv
        if brake_active and current != PRICE_EXPENSIVE:
            future_window = categories[i + 1 : i + 1 + bridge_max_slots]
            if PRICE_EXPENSIVE in future_window:
                states.append("HOLD")
                continue

            brake_active = False
            states.append("RAMP_DOWN")
            continue

        # Pre-brake: starta innan dyrperiod, men bara om bromsen inte redan är aktiv
        if not brake_active and current != PRICE_EXPENSIVE and next_cat == PRICE_EXPENSIVE:
            brake_active = True
            states.append("PRE_BRAKE")
            continue

        states.append("NORMAL")

    return states


def test_prebrake_starts_before_expensive():
    categories = [
        PRICE_NORMAL,
        PRICE_NORMAL,
        PRICE_EXPENSIVE,
        PRICE_EXPENSIVE,
    ]

    states = simulate_brake_states(categories)

    assert states == [
        "NORMAL",
        "PRE_BRAKE",
        "PRICE_BRAKE",
        "PRICE_BRAKE",
    ]


def test_brake_holds_while_price_is_above_p80():
    categories = [
        PRICE_NORMAL,
        PRICE_EXPENSIVE,
        PRICE_EXPENSIVE,
        PRICE_EXPENSIVE,
        PRICE_NORMAL,
    ]

    states = simulate_brake_states(categories)

    assert states[1] == "PRICE_BRAKE"
    assert states[2] == "PRICE_BRAKE"
    assert states[3] == "PRICE_BRAKE"


def test_brake_releases_after_expensive_period():
    categories = [
        PRICE_NORMAL,
        PRICE_EXPENSIVE,
        PRICE_EXPENSIVE,
        PRICE_NORMAL,
        PRICE_NORMAL,
    ]

    states = simulate_brake_states(categories)

    assert states == [
        "PRE_BRAKE",
        "PRICE_BRAKE",
        "PRICE_BRAKE",
        "RAMP_DOWN",
        "NORMAL",
    ]


def test_short_cheap_dip_does_not_release_brake():
    categories = [
        PRICE_NORMAL,
        PRICE_EXPENSIVE,
        PRICE_CHEAP,
        PRICE_EXPENSIVE,
        PRICE_NORMAL,
    ]

    states = simulate_brake_states(categories, bridge_max_slots=2)

    assert states == [
        "PRE_BRAKE",
        "PRICE_BRAKE",
        "HOLD",
        "PRICE_BRAKE",
        "RAMP_DOWN",
    ]


def test_long_cheap_period_releases_brake():
    categories = [
        PRICE_NORMAL,
        PRICE_EXPENSIVE,
        PRICE_CHEAP,
        PRICE_CHEAP,
        PRICE_CHEAP,
        PRICE_EXPENSIVE,
    ]

    states = simulate_brake_states(categories, bridge_max_slots=2)

    assert states == [
        "PRE_BRAKE",
        "PRICE_BRAKE",
        "RAMP_DOWN",
        "NORMAL",
        "PRE_BRAKE",
        "PRICE_BRAKE",
    ]