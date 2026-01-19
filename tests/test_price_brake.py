from custom_components.pumpsteer.price_brake import (
    compute_block_area,
    compute_brake_level,
    compute_price_brake,
    detect_expensive_blocks,
    select_price_block,
)


def test_single_spike_no_block():
    forward_prices = [1.0, 1.0, 2.0, 1.0, 1.0, 1.0]

    result = compute_price_brake(
        forward_prices=forward_prices,
        dt_minutes=15,
        threshold_delta=0.3,
        threshold_percentile=None,
        min_block_duration_min=60,
        pre_brake_minutes=60,
        post_release_minutes=60,
        area_scale=4.0,
        now_offset_minutes=0.0,
    )

    assert result["block"] is None
    assert result["brake_level"] == 0.0
    assert result["amplitude"] == 0.0


def test_brake_ramps_around_expensive_block():
    forward_prices = [1.0, 1.0, 3.0, 3.0, 1.0, 1.0]

    result = compute_price_brake(
        forward_prices=forward_prices,
        dt_minutes=60,
        threshold_delta=0.3,
        threshold_percentile=None,
        min_block_duration_min=60,
        pre_brake_minutes=60,
        post_release_minutes=60,
        area_scale=4.0,
        now_offset_minutes=0.0,
    )
    block = result["block"]

    assert block is not None

    amplitude = result["amplitude"]
    ramp_up = compute_brake_level(block, amplitude, 60, 60, now_offset_minutes=90)
    at_start = compute_brake_level(block, amplitude, 60, 60, now_offset_minutes=120)
    ramp_down = compute_brake_level(block, amplitude, 60, 60, now_offset_minutes=270)

    assert 0.0 < ramp_up < amplitude
    assert at_start == amplitude
    assert 0.0 < ramp_down < amplitude
    for value in (ramp_up, at_start, ramp_down):
        assert 0.0 <= value <= 1.0


def test_area_drives_amplitude():
    prices = [1.0, 3.0, 3.0, 3.0, 1.0]
    threshold = 1.3

    short_block = compute_block_area(prices, 1, 1, threshold, 60)
    long_block = compute_block_area(prices, 1, 3, threshold, 60)

    short_amplitude = min(short_block.area / 4.0, 1.0)
    long_amplitude = min(long_block.area / 4.0, 1.0)

    assert long_block.area > short_block.area
    assert long_amplitude > short_amplitude


def test_selects_largest_area_block():
    forward_prices = [1.0, 2.0, 1.0, 4.0, 4.0, 1.0]
    threshold = 1.5

    blocks = detect_expensive_blocks(
        forward_prices, threshold, dt_minutes=60, min_block_duration_min=60
    )
    selected = select_price_block(blocks)

    assert selected is not None
    assert selected.start_index == 3
