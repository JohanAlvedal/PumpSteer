#include <cassert>
#include <cmath>
#include <iostream>

#include "pumpsteer/controller.h"

namespace {

pumpsteer::ControlInput baseInput() {
    pumpsteer::ControlInput input;
    input.indoor_temp_c = 21.0F;
    input.outdoor_temp_c = 2.0F;
    input.target_temp_c = 21.0F;
    input.indoor_valid = true;
    input.outdoor_valid = true;
    input.price_valid = true;
    input.forecast_valid = true;
    input.aggressiveness = 3;
    input.monotonic_ms = 60000;
    return input;
}

void testSafeMode() {
    pumpsteer::Controller controller;
    auto input = baseInput();
    input.indoor_valid = false;

    const auto output = controller.update(input);
    assert(output.mode == pumpsteer::OperatingMode::Safe);
    assert(output.bypass_requested);
    assert(std::fabs(output.fake_outdoor_temp_c - input.outdoor_temp_c) < 0.001F);
}

void testPiHeatingDemand() {
    pumpsteer::Controller controller;
    auto input = baseInput();
    input.indoor_temp_c = 20.0F;

    const auto output = controller.update(input);
    assert(output.mode == pumpsteer::OperatingMode::Normal);
    assert(output.fake_outdoor_temp_c < input.outdoor_temp_c);
    assert(output.heating_demand_c > 0.0F);
}

void testAggressivenessZeroDisablesPriceControl() {
    pumpsteer::Controller controller;
    auto input = baseInput();
    input.aggressiveness = 0;
    input.price_class = pumpsteer::PriceClass::Expensive;

    const auto output = controller.update(input);
    assert(output.mode == pumpsteer::OperatingMode::Normal);
    assert(!output.price_control_active);
    assert(output.brake_factor == 0.0F);
}

void testExpensivePriceStartsBrake() {
    pumpsteer::Controller controller;
    auto input = baseInput();
    input.price_class = pumpsteer::PriceClass::Expensive;

    const auto output = controller.update(input);
    assert(output.mode == pumpsteer::OperatingMode::Braking);
    assert(output.brake_factor > 0.0F);
    assert(output.fake_outdoor_temp_c > input.outdoor_temp_c);
}

void testComfortFloorBlocksBrake() {
    pumpsteer::Controller controller;
    auto input = baseInput();
    input.indoor_temp_c = 18.0F;
    input.price_class = pumpsteer::PriceClass::Expensive;

    const auto output = controller.update(input);
    assert(output.mode == pumpsteer::OperatingMode::Normal);
    assert(output.brake_factor == 0.0F);
    assert(output.fake_outdoor_temp_c < input.outdoor_temp_c);
}

void testPreheatBoost() {
    pumpsteer::Controller controller;
    auto input = baseInput();
    input.upcoming_expensive = true;
    input.minutes_until_expensive = 120.0F;
    input.forecast_cold = true;
    input.preheat_strength = 0.5F;

    const auto output = controller.update(input);
    assert(output.mode == pumpsteer::OperatingMode::Preheating);
    assert(std::fabs(output.preheat_boost_c - 2.0F) < 0.001F);
    assert(output.fake_outdoor_temp_c < input.outdoor_temp_c);
}

void testSummerPassthrough() {
    pumpsteer::Controller controller;
    auto input = baseInput();
    input.outdoor_temp_c = 20.0F;

    const auto output = controller.update(input);
    assert(output.mode == pumpsteer::OperatingMode::Summer);
    assert(std::fabs(output.fake_outdoor_temp_c - input.outdoor_temp_c) < 0.001F);
}

}  // namespace

int main() {
    testSafeMode();
    testPiHeatingDemand();
    testAggressivenessZeroDisablesPriceControl();
    testExpensivePriceStartsBrake();
    testComfortFloorBlocksBrake();
    testPreheatBoost();
    testSummerPassthrough();

    std::cout << "PumpSteer Mini core tests passed\n";
    return 0;
}
