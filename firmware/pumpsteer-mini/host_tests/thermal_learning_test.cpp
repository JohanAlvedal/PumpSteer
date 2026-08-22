#include <cassert>
#include <cmath>
#include <iostream>

#include "pumpsteer/thermal_learning.h"

namespace {

void testAcceptsValidReducedHeatingObservation() {
    pumpsteer::learning::ThermalLearner learner;

    pumpsteer::learning::Observation observation;
    observation.indoor_start_c = 21.0F;
    observation.indoor_end_c = 20.5F;
    observation.outdoor_average_c = 1.0F;
    observation.duration_hours = 1.0F;
    observation.reduced_heating_window = true;

    assert(learner.observe(observation));
    const auto& model = learner.model();
    assert(model.accepted_samples == 1U);
    assert(std::fabs(model.heat_loss_coefficient_per_hour - 0.025F) < 0.0001F);
    assert(model.confidence > 0.0F);
}

void testRejectsUnqualifiedObservation() {
    pumpsteer::learning::ThermalLearner learner;

    pumpsteer::learning::Observation observation;
    observation.indoor_start_c = 21.0F;
    observation.indoor_end_c = 20.8F;
    observation.outdoor_average_c = 5.0F;
    observation.duration_hours = 1.0F;
    observation.reduced_heating_window = false;

    assert(!learner.observe(observation));
    assert(learner.model().accepted_samples == 0U);
}

void testPredictDropIsDiagnosticOnly() {
    pumpsteer::learning::ThermalLearner learner;

    pumpsteer::learning::Observation observation;
    observation.indoor_start_c = 21.0F;
    observation.indoor_end_c = 20.5F;
    observation.outdoor_average_c = 1.0F;
    observation.duration_hours = 1.0F;
    observation.reduced_heating_window = true;
    assert(learner.observe(observation));

    const float predicted = learner.predictDropC(21.0F, 1.0F, 2.0F);
    assert(std::fabs(predicted - 1.0F) < 0.0001F);
}

void testRestoreRejectsInvalidModel() {
    pumpsteer::learning::ThermalLearner learner;

    pumpsteer::learning::ThermalModel model;
    model.heat_loss_coefficient_per_hour = 10.0F;
    model.confidence = 1.0F;
    model.accepted_samples = 99U;

    learner.restore(model);
    assert(learner.model().accepted_samples == 0U);
}

}  // namespace

int main() {
    testAcceptsValidReducedHeatingObservation();
    testRejectsUnqualifiedObservation();
    testPredictDropIsDiagnosticOnly();
    testRestoreRejectsInvalidModel();

    std::cout << "PumpSteer Mini thermal learning tests passed\n";
    return 0;
}
