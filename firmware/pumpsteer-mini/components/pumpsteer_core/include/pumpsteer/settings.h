#pragma once

#include <array>
#include <cstdint>

namespace pumpsteer {

struct Settings {
    static constexpr float kMinFakeTempC = -20.0F;
    static constexpr float kMaxFakeTempC = 25.0F;

    static constexpr float kPidKp = 2.4F;
    static constexpr float kPidKi = 0.035F;
    static constexpr float kPidIntegralClamp = 6.0F;
    static constexpr float kPidOutputClamp = 12.0F;

    static constexpr float kBrakeDeltaC = 10.0F;
    static constexpr float kBrakeHoldMinutes = 30.0F;
    static constexpr float kRampScale = 6.0F;
    static constexpr float kRampMinMinutes = 15.0F;
    static constexpr float kRampMaxMinutes = 60.0F;
    static constexpr float kRampOutFactor = 0.5F;
    static constexpr float kBrakeRampMaxDtSeconds = 60.0F;

    static constexpr float kPreheatBoostC = 4.0F;

    static constexpr float kDefaultSummerThresholdC = 18.0F;
    static constexpr float kDefaultTargetTempC = 21.0F;
    static constexpr float kDefaultHouseInertia = 2.0F;
    static constexpr std::uint8_t kDefaultAggressiveness = 3;

    static constexpr std::array<float, 6> kComfortDropByAggressiveness = {
        0.0F,
        0.5F,
        1.0F,
        1.5F,
        2.0F,
        3.0F,
    };
};

}  // namespace pumpsteer
