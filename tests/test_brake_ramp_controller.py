from custom_components.pumpsteer.brake_ramp_controller import (
    BrakeRampController,
    BrakePhase,
)


def test_bridge_hold_prevents_flicker_on_short_false_pulse():
    controller = BrakeRampController()
    now = 0.0

    for _ in range(3):
        now += 30
        result = controller.update(
            now_ts=now,
            brake_request=True,
            near_brake=False,
            hold_offset_c=0.6,
            max_delta_per_step_c=0.2,
        )

    assert result.phase == BrakePhase.HOLDING.value
    assert result.offset_c == 0.6

    now += 30
    bridge_result = controller.update(
        now_ts=now,
        brake_request=False,
        near_brake=True,
        hold_offset_c=0.6,
        max_delta_per_step_c=0.2,
    )

    assert bridge_result.phase == BrakePhase.HOLDING.value
    assert bridge_result.offset_c == 0.6
    assert bridge_result.reason_code == "BRAKE_BRIDGE_HOLD"


def test_normal_ramp_up_hold_and_ramp_down():
    controller = BrakeRampController()
    now = 0.0

    now += 30
    r1 = controller.update(
        now_ts=now,
        brake_request=True,
        near_brake=False,
        hold_offset_c=0.6,
        max_delta_per_step_c=0.2,
    )
    assert r1.phase == BrakePhase.RAMPING_UP.value
    assert r1.offset_c == 0.2

    now += 30
    r2 = controller.update(
        now_ts=now,
        brake_request=True,
        near_brake=False,
        hold_offset_c=0.6,
        max_delta_per_step_c=0.2,
    )
    assert r2.phase == BrakePhase.RAMPING_UP.value
    assert r2.offset_c == 0.4

    now += 30
    r3 = controller.update(
        now_ts=now,
        brake_request=True,
        near_brake=False,
        hold_offset_c=0.6,
        max_delta_per_step_c=0.2,
    )
    assert r3.phase == BrakePhase.HOLDING.value
    assert r3.offset_c == 0.6

    now += 30
    d1 = controller.update(
        now_ts=now,
        brake_request=False,
        near_brake=False,
        hold_offset_c=0.6,
        max_delta_per_step_c=0.2,
    )
    assert d1.phase == BrakePhase.RAMPING_DOWN.value
    assert d1.offset_c == 0.4

    now += 30
    d2 = controller.update(
        now_ts=now,
        brake_request=False,
        near_brake=False,
        hold_offset_c=0.6,
        max_delta_per_step_c=0.2,
    )
    assert d2.phase == BrakePhase.RAMPING_DOWN.value
    assert d2.offset_c == 0.2

    now += 30
    d3 = controller.update(
        now_ts=now,
        brake_request=False,
        near_brake=False,
        hold_offset_c=0.6,
        max_delta_per_step_c=0.2,
    )
    assert d3.phase == BrakePhase.IDLE.value
    assert d3.offset_c == 0.0
