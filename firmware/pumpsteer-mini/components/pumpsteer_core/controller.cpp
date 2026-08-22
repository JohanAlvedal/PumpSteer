#include "pumpsteer/controller.h"

#include <algorithm>
#include <cmath>
#include <limits>

#include "pumpsteer/settings.h"

namespace pumpsteer {

namespace {

bool validTemperature(const float value) {
    return std::isfinite(value) && value >= -50.0F && value <= 60.0F;
}

}  // namespace

void Controller::reset(const std::uint64_t now_ms) {
    pi_.reset(now_ms);
    brake_ramp_ = 0.0F;
    brake_last_update_ms_ = now_ms;
    brake_last_requested_ms_ = 0;
    brake_timing_initialized_ = true;
}

float Controller::clampFakeTemperature(const float value) {
    return std::clamp(value, Settings::kMinFakeTempC, Settings::kMaxFakeTempC);
}

std::uint8_t Controller::clampAggressiveness(const std::uint8_t value) {
    return std::min<std::uint8_t>(value, 5);
}

float Controller::comfortFloor(
    const float target_temp_c,
    const std::uint8_t aggressiveness) {
    const auto level = clampAggressiveness(aggressiveness);
    return target_temp_c - Settings::kComfortDropByAggressiveness[level];
}

float Controller::rampInMinutes(const float house_inertia) {
    const float inertia = std::clamp(house_inertia, 0.5F, 10.0F);
    return std::clamp(
        inertia * Settings::kRampScale,
        Settings::kRampMinMinutes,
        Settings::kRampMaxMinutes);
}

float Controller::updateBrakeRamp(
    const bool requested,
    const bool force_release,
    const std::uint64_t now_ms,
    const float ramp_in_minutes,
    const float ramp_out_minutes) {
    float dt_seconds = Settings::kBrakeRampMaxDtSeconds;
    if (brake_timing_initialized_) {
        const std::uint64_t elapsed_ms =
            now_ms >= brake_last_update_ms_ ? now_ms - brake_last_update_ms_ : 0;
        dt_seconds = std::clamp(
            static_cast<float>(elapsed_ms) / 1000.0F,
            1.0F,
            Settings::kBrakeRampMaxDtSeconds);
    }

    brake_timing_initialized_ = true;
    brake_last_update_ms_ = now_ms;

    if (requested) {
        brake_last_requested_ms_ = now_ms;
        brake_ramp_ += dt_seconds / (ramp_in_minutes * 60.0F);
    } else {
        const bool hold_active =
            !force_release &&
            brake_last_requested_ms_ != 0 &&
            now_ms >= brake_last_requested_ms_ &&
            (now_ms - brake_last_requested_ms_) <
                static_cast<std::uint64_t>(Settings::kBrakeHoldMinutes * 60000.0F);

        if (!hold_active) {
            brake_ramp_ -= dt_seconds / (ramp_out_minutes * 60.0F);
        }
    }

    brake_ramp_ = std::clamp(brake_ramp_, 0.0F, 1.0F);
    return brake_ramp_;
}

ControlOutput Controller::makePiOutput(
    const ControlInput& input,
    const OperatingMode mode,
    const bool freeze_integral,
    const float extra_heating_demand_c) {
    const PIResult pi = pi_.compute(
        input.target_temp_c,
        input.indoor_temp_c,
        input.monotonic_ms,
        freeze_integral);

    const float base_heating_demand = -pi.offset;
    const float heating_demand = base_heating_demand + extra_heating_demand_c;
    const float fake_temp = clampFakeTemperature(input.outdoor_temp_c - heating_demand);

    ControlOutput output;
    output.fake_outdoor_temp_c = fake_temp;
    output.heating_demand_c = heating_demand;
    output.pi_error_c = pi.error;
    output.pi_p_term = pi.p_term;
    output.pi_i_term = pi.i_term;
    output.brake_factor = brake_ramp_;
    output.preheat_boost_c = extra_heating_demand_c;
    output.comfort_floor_c = comfortFloor(input.target_temp_c, input.aggressiveness);
    output.mode = mode;
    output.bypass_requested = false;
    output.price_control_active = input.price_valid && input.aggressiveness > 0;
    return output;
}

ControlOutput Controller::update(const ControlInput& input) {
    const bool indoor_ok = input.indoor_valid && validTemperature(input.indoor_temp_c);
    const bool outdoor_ok = input.outdoor_valid && validTemperature(input.outdoor_temp_c);

    if (!indoor_ok || !outdoor_ok) {
        ControlOutput output;
        output.mode = OperatingMode::Safe;
        output.bypass_requested = true;
        output.degraded = true;
        output.fake_outdoor_temp_c = outdoor_ok
            ? clampFakeTemperature(input.outdoor_temp_c)
            : std::numeric_limits<float>::quiet_NaN();
        reset(input.monotonic_ms);
        return output;
    }

    const std::uint8_t aggressiveness = clampAggressiveness(input.aggressiveness);
    const float comfort_floor = comfortFloor(input.target_temp_c, aggressiveness);
    const float ramp_in = rampInMinutes(input.house_inertia);
    const float ramp_out = std::max(
        Settings::kRampMinMinutes,
        ramp_in * Settings::kRampOutFactor);

    if (input.outdoor_temp_c >= input.summer_threshold_c) {
        reset(input.monotonic_ms);
        ControlOutput output;
        output.fake_outdoor_temp_c = clampFakeTemperature(input.outdoor_temp_c);
        output.comfort_floor_c = comfort_floor;
        output.mode = OperatingMode::Summer;
        output.bypass_requested = false;
        output.degraded = !input.price_valid || !input.forecast_valid;
        return output;
    }

    if (aggressiveness == 0 || !input.price_valid) {
        updateBrakeRamp(false, true, input.monotonic_ms, ramp_in, ramp_out);
        ControlOutput output = makePiOutput(
            input,
            OperatingMode::Normal,
            false);
        output.degraded = !input.price_valid;
        output.price_control_active = false;
        return output;
    }

    if (input.price_class == PriceClass::Expensive) {
        const bool comfort_allows_brake = input.indoor_temp_c >= comfort_floor;
        const float factor = updateBrakeRamp(
            comfort_allows_brake,
            !comfort_allows_brake,
            input.monotonic_ms,
            ramp_in,
            ramp_out);

        ControlOutput output = makePiOutput(
            input,
            factor > 0.0F ? OperatingMode::Braking : OperatingMode::Normal,
            factor > 0.0F);

        if (factor > 0.0F) {
            const float brake_temp = clampFakeTemperature(
                input.outdoor_temp_c + Settings::kBrakeDeltaC);
            output.fake_outdoor_temp_c = clampFakeTemperature(
                output.fake_outdoor_temp_c +
                (brake_temp - output.fake_outdoor_temp_c) * factor);
            output.brake_factor = factor;
        }

        output.comfort_floor_c = comfort_floor;
        output.price_control_active = true;
        return output;
    }

    if (input.upcoming_expensive &&
        input.minutes_until_expensive >= 0.0F &&
        input.minutes_until_expensive <= ramp_in) {
        const float factor = updateBrakeRamp(
            true,
            false,
            input.monotonic_ms,
            ramp_in,
            ramp_out);

        ControlOutput output = makePiOutput(
            input,
            OperatingMode::PreBraking,
            true);
        const float brake_temp = clampFakeTemperature(
            input.outdoor_temp_c + Settings::kBrakeDeltaC);
        output.fake_outdoor_temp_c = clampFakeTemperature(
            output.fake_outdoor_temp_c +
            (brake_temp - output.fake_outdoor_temp_c) * factor);
        output.brake_factor = factor;
        output.price_control_active = true;
        return output;
    }

    if (input.upcoming_expensive &&
        input.preheat_enabled &&
        input.forecast_valid &&
        input.forecast_cold) {
        updateBrakeRamp(false, false, input.monotonic_ms, ramp_in, ramp_out);
        const float strength = std::clamp(input.preheat_strength, 0.0F, 1.0F);
        const float boost = Settings::kPreheatBoostC * strength;
        ControlOutput output = makePiOutput(
            input,
            OperatingMode::Preheating,
            false,
            boost);
        output.degraded = false;
        output.price_control_active = true;
        return output;
    }

    const bool comfort_requires_release = input.indoor_temp_c < comfort_floor;
    const float factor = updateBrakeRamp(
        false,
        comfort_requires_release,
        input.monotonic_ms,
        ramp_in,
        ramp_out);

    ControlOutput output = makePiOutput(
        input,
        OperatingMode::Normal,
        factor > 0.0F);

    if (factor > 0.0F) {
        const float brake_temp = clampFakeTemperature(
            input.outdoor_temp_c + Settings::kBrakeDeltaC);
        output.fake_outdoor_temp_c = clampFakeTemperature(
            output.fake_outdoor_temp_c +
            (brake_temp - output.fake_outdoor_temp_c) * factor);
        output.brake_factor = factor;
    }

    output.degraded = !input.forecast_valid;
    output.price_control_active = true;

    // Precooling is intentionally reserved in the public API but not activated yet.
    // The correct Ohmigo output direction depends on the heat pump cooling behavior.
    return output;
}

}  // namespace pumpsteer
