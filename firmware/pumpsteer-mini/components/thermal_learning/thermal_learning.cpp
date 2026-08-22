#include "pumpsteer/thermal_learning.h"

#include <algorithm>
#include <cmath>

namespace pumpsteer::learning {

namespace {

constexpr float kMinimumDurationHours = 0.25F;
constexpr float kMaximumDurationHours = 6.0F;
constexpr float kMinimumIndoorOutdoorDeltaC = 3.0F;
constexpr float kMinimumObservedDropC = 0.02F;
constexpr float kMaximumObservedDropC = 5.0F;
constexpr float kMaximumHeatLossCoefficientPerHour = 0.25F;
constexpr float kSamplesForFullConfidence = 40.0F;
constexpr float kMinimumAdaptiveAlpha = 0.05F;
constexpr float kMaximumAdaptiveAlpha = 0.25F;

bool finite(const float value) {
    return std::isfinite(value);
}

}  // namespace

void ThermalLearner::reset() {
    model_ = ThermalModel{};
}

bool ThermalLearner::observe(const Observation& observation) {
    if (!observation.reduced_heating_window ||
        !finite(observation.indoor_start_c) ||
        !finite(observation.indoor_end_c) ||
        !finite(observation.outdoor_average_c) ||
        !finite(observation.duration_hours)) {
        return false;
    }

    if (observation.duration_hours < kMinimumDurationHours ||
        observation.duration_hours > kMaximumDurationHours) {
        return false;
    }

    const float indoor_outdoor_delta =
        observation.indoor_start_c - observation.outdoor_average_c;
    if (indoor_outdoor_delta < kMinimumIndoorOutdoorDeltaC) {
        return false;
    }

    const float observed_drop =
        observation.indoor_start_c - observation.indoor_end_c;
    if (observed_drop < kMinimumObservedDropC ||
        observed_drop > kMaximumObservedDropC) {
        return false;
    }

    const float sample = observed_drop /
        (indoor_outdoor_delta * observation.duration_hours);
    if (!finite(sample) || sample <= 0.0F ||
        sample > kMaximumHeatLossCoefficientPerHour) {
        return false;
    }

    if (model_.accepted_samples == 0) {
        model_.heat_loss_coefficient_per_hour = sample;
    } else {
        const float exact_mean_alpha =
            1.0F / static_cast<float>(model_.accepted_samples + 1U);
        const float alpha = std::clamp(
            exact_mean_alpha,
            kMinimumAdaptiveAlpha,
            kMaximumAdaptiveAlpha);
        model_.heat_loss_coefficient_per_hour =
            (1.0F - alpha) * model_.heat_loss_coefficient_per_hour +
            alpha * sample;
    }

    ++model_.accepted_samples;
    model_.confidence = std::clamp(
        static_cast<float>(model_.accepted_samples) / kSamplesForFullConfidence,
        0.0F,
        1.0F);

    return true;
}

const ThermalModel& ThermalLearner::model() const {
    return model_;
}

float ThermalLearner::predictDropC(
    const float indoor_c,
    const float outdoor_c,
    const float duration_hours) const {
    if (!finite(indoor_c) || !finite(outdoor_c) || !finite(duration_hours) ||
        duration_hours <= 0.0F || model_.accepted_samples == 0) {
        return 0.0F;
    }

    const float indoor_outdoor_delta = std::max(0.0F, indoor_c - outdoor_c);
    return model_.heat_loss_coefficient_per_hour *
        indoor_outdoor_delta * duration_hours;
}

void ThermalLearner::restore(const ThermalModel& model) {
    if (!finite(model.heat_loss_coefficient_per_hour) ||
        !finite(model.confidence) ||
        model.heat_loss_coefficient_per_hour < 0.0F ||
        model.heat_loss_coefficient_per_hour > kMaximumHeatLossCoefficientPerHour) {
        reset();
        return;
    }

    model_ = model;
    model_.confidence = std::clamp(model_.confidence, 0.0F, 1.0F);
}

}  // namespace pumpsteer::learning
