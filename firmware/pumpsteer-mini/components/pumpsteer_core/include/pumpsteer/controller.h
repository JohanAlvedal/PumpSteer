#pragma once

#include <cstdint>

#include "pumpsteer/pi_controller.h"
#include "pumpsteer/types.h"

namespace pumpsteer {

class Controller {
public:
    ControlOutput update(const ControlInput& input);
    void reset(std::uint64_t now_ms);

private:
    static float clampFakeTemperature(float value);
    static std::uint8_t clampAggressiveness(std::uint8_t value);
    static float comfortFloor(float target_temp_c, std::uint8_t aggressiveness);
    static float rampInMinutes(float house_inertia);

    float updateBrakeRamp(
        bool requested,
        bool force_release,
        std::uint64_t now_ms,
        float ramp_in_minutes,
        float ramp_out_minutes);

    ControlOutput makePiOutput(
        const ControlInput& input,
        OperatingMode mode,
        bool freeze_integral,
        float extra_heating_demand_c = 0.0F);

    PIController pi_;
    float brake_ramp_ = 0.0F;
    std::uint64_t brake_last_update_ms_ = 0;
    std::uint64_t brake_last_requested_ms_ = 0;
    bool brake_timing_initialized_ = false;
};

}  // namespace pumpsteer
