from custom_components.pumpsteer.pi_controller import (
    apply_rate_limit,
    compute_price_baseline,
    compute_price_pressure,
    update_pi_output,
)


def test_price_pressure_longer_peak_is_stronger():
    baseline = 1.0
    short_spike = [1.0, 1.0, 5.0, 1.0, 1.0, 1.0]
    long_peak = [1.0, 5.0, 5.0, 5.0, 5.0, 5.0]

    short_pressure = compute_price_pressure(short_spike, 0, 6, baseline)
    long_pressure = compute_price_pressure(long_peak, 0, 6, baseline)

    assert long_pressure > short_pressure


def test_price_baseline_uses_median_window():
    prices = [1.0, 1.2, 5.0, 1.1, 1.0]
    baseline = compute_price_baseline(prices, 0, 5)

    assert baseline == 1.1


def test_price_rate_limit_caps_change():
    limited, rate_limited = apply_rate_limit(0.6, 0.0, 0.1)

    assert limited == 0.1
    assert rate_limited is True


def test_comfort_pi_integrates_and_clamps():
    output, integral, saturated_high, saturated_low = update_pi_output(
        value=1.0,
        integral=0.0,
        kp=0.6,
        ki=0.1,
        dt_hours=1.0,
        output_min=-1.0,
        output_max=1.0,
    )

    assert output > 0.6
    assert integral > 0.0
    assert not saturated_high
    assert not saturated_low

    output, integral, saturated_high, _ = update_pi_output(
        value=10.0,
        integral=integral,
        kp=0.6,
        ki=0.1,
        dt_hours=1.0,
        output_min=-1.0,
        output_max=1.0,
    )

    assert output == 1.0
    assert saturated_high
    assert integral < 2.0
