#include "pumpsteer/pi_controller.h"

#include <algorithm>

#include "pumpsteer/settings.h"

namespace pumpsteer {

void PIController::reset(const std::uint64_t now_ms) {
    integral_ = 0.0F;
    last_error_ = 0.0F;
    last_time_ms_ = now_ms;
    initialized_ = true;
}

PIResult PIController::compute(
    const float target_temp_c,
    const float indoor_temp_c,
    const std::uint64_t now_ms,
    const bool freeze_integral) {
    float dt_minutes = 1.0F;
    if (initialized_) {
        const std::uint64_t elapsed_ms = now_ms >= last_time_ms_ ? now_ms - last_time_ms_ : 0;
        dt_minutes = std::max(static_cast<float>(elapsed_ms) / 60000.0F, 0.01F);
    }

    initialized_ = true;
    last_time_ms_ = now_ms;

    const float error = target_temp_c - indoor_temp_c;
    const float p_term = Settings::kPidKp * error;

    if (!freeze_integral) {
        integral_ += Settings::kPidKi * error * dt_minutes;
        integral_ = std::clamp(
            integral_,
            -Settings::kPidIntegralClamp,
            Settings::kPidIntegralClamp);
    }

    last_error_ = error;

    const float raw_output = -(p_term + integral_);
    const float offset = std::clamp(
        raw_output,
        -Settings::kPidOutputClamp,
        Settings::kPidOutputClamp);

    return PIResult{
        .offset = offset,
        .p_term = p_term,
        .i_term = integral_,
        .error = error,
    };
}

}  // namespace pumpsteer
