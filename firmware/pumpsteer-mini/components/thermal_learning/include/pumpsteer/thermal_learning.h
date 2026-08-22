#pragma once

#include <cstdint>

namespace pumpsteer::learning {

struct Observation {
    float indoor_start_c = 0.0F;
    float indoor_end_c = 0.0F;
    float outdoor_average_c = 0.0F;
    float duration_hours = 0.0F;
    bool reduced_heating_window = false;
};

struct ThermalModel {
    float heat_loss_coefficient_per_hour = 0.0F;
    float confidence = 0.0F;
    std::uint32_t accepted_samples = 0;
};

class ThermalLearner {
public:
    void reset();

    // Accepts carefully filtered observation windows and updates an explainable
    // heat-loss estimate. The learner does not modify controller parameters.
    bool observe(const Observation& observation);

    [[nodiscard]] const ThermalModel& model() const;

    // Predicts passive indoor-temperature drop using the learned heat-loss
    // coefficient. This is diagnostic/shadow-mode output until explicitly wired
    // into bounded control assistance in a later milestone.
    [[nodiscard]] float predictDropC(
        float indoor_c,
        float outdoor_c,
        float duration_hours) const;

    void restore(const ThermalModel& model);

private:
    ThermalModel model_{};
};

}  // namespace pumpsteer::learning
