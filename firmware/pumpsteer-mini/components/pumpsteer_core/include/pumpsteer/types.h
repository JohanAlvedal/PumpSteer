#pragma once

#include <cstdint>
#include <limits>

#include "pumpsteer/settings.h"

namespace pumpsteer {

enum class OperatingMode : std::uint8_t {
    Safe,
    Summer,
    Normal,
    Preheating,
    PreBraking,
    Braking,
    Precooling,
};

enum class PriceClass : std::uint8_t {
    Cheap,
    Normal,
    Expensive,
};

struct ControlInput {
    float indoor_temp_c = std::numeric_limits<float>::quiet_NaN();
    float outdoor_temp_c = std::numeric_limits<float>::quiet_NaN();
    float target_temp_c = Settings::kDefaultTargetTempC;
    float summer_threshold_c = Settings::kDefaultSummerThresholdC;
    float house_inertia = Settings::kDefaultHouseInertia;
    std::uint8_t aggressiveness = Settings::kDefaultAggressiveness;

    bool indoor_valid = false;
    bool outdoor_valid = false;

    bool price_valid = false;
    PriceClass price_class = PriceClass::Normal;
    bool upcoming_expensive = false;
    float minutes_until_expensive = -1.0F;

    bool forecast_valid = false;
    bool forecast_cold = false;
    bool precool_worthwhile = false;
    float preheat_strength = 1.0F;

    bool preheat_enabled = true;
    bool cooling_enabled = false;

    std::uint64_t monotonic_ms = 0;
};

struct ControlOutput {
    float fake_outdoor_temp_c = std::numeric_limits<float>::quiet_NaN();
    float heating_demand_c = 0.0F;
    float pi_error_c = 0.0F;
    float pi_p_term = 0.0F;
    float pi_i_term = 0.0F;
    float brake_factor = 0.0F;
    float preheat_boost_c = 0.0F;
    float comfort_floor_c = 0.0F;

    OperatingMode mode = OperatingMode::Safe;

    bool bypass_requested = true;
    bool degraded = false;
    bool price_control_active = false;
};

}  // namespace pumpsteer
