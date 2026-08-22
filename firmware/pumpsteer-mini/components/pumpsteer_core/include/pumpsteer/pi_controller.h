#pragma once

#include <cstdint>

namespace pumpsteer {

struct PIResult {
    float offset = 0.0F;
    float p_term = 0.0F;
    float i_term = 0.0F;
    float error = 0.0F;
};

class PIController {
public:
    void reset(std::uint64_t now_ms);

    PIResult compute(
        float target_temp_c,
        float indoor_temp_c,
        std::uint64_t now_ms,
        bool freeze_integral);

private:
    float integral_ = 0.0F;
    float last_error_ = 0.0F;
    std::uint64_t last_time_ms_ = 0;
    bool initialized_ = false;
};

}  // namespace pumpsteer
