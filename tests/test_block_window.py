from datetime import datetime, timedelta

from custom_components.pumpsteer.price_brake import PriceBlock
from custom_components.pumpsteer.sensor.sensor import compute_block_window


def test_compute_block_window_active_now():
    update_time = datetime(2024, 1, 1, 12, 0, 0)
    block = PriceBlock(
        start_index=0,
        end_index=1,
        dt_minutes=60,
        area=1.5,
        peak=2.5,
    )

    block_start, block_end, in_price_block, block_state = compute_block_window(
        update_time, block
    )

    assert block_start == update_time
    assert block_end == update_time + timedelta(minutes=120)
    assert in_price_block is True
    assert block_state == "active"
