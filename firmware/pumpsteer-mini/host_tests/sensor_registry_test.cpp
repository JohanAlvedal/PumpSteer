#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>

#include "pumpsteer/bthome.h"
#include "pumpsteer/sensor_registry.h"

namespace {

pumpsteer::ble::SensorAddress makeAddress(const std::uint8_t suffix) {
    pumpsteer::ble::SensorAddress address{};
    address.bytes = {0x10, 0x20, 0x30, 0x40, 0x50, suffix};
    address.type = 1;
    return address;
}

pumpsteer::bthome::Reading makeReading(
    const float temperature,
    const std::uint8_t packet_id) {
    pumpsteer::bthome::Reading reading{};
    reading.has_temperature = true;
    reading.temperature_c = temperature;
    reading.has_packet_id = true;
    reading.packet_id = packet_id;
    reading.has_battery = true;
    reading.battery_percent = 90;
    return reading;
}

void testDiscoveryAndDuplicateHandling() {
    pumpsteer::ble::SensorRegistry registry;
    const auto address = makeAddress(0x60);

    auto result = registry.update(address, "Shelly BLU H&T", -52, makeReading(21.4F, 7), 1000);
    assert(result == pumpsteer::ble::RegistryUpdate::Added);
    assert(registry.count() == 1);

    result = registry.update(address, "Shelly BLU H&T", -50, makeReading(99.0F, 7), 2000);
    assert(result == pumpsteer::ble::RegistryUpdate::SeenDuplicate);

    const auto* sensor = registry.find(address);
    assert(sensor != nullptr);
    assert(std::fabs(sensor->temperature_c - 21.4F) < 0.001F);
    assert(sensor->rssi == -50);
    assert(sensor->last_seen_ms == 2000);

    result = registry.update(address, "Shelly BLU H&T", -49, makeReading(21.7F, 8), 3000);
    assert(result == pumpsteer::ble::RegistryUpdate::Updated);
    assert(std::fabs(registry.find(address)->temperature_c - 21.7F) < 0.001F);
}

void testRoleAssignmentAndFreshness() {
    pumpsteer::ble::SensorRegistry registry;
    const auto indoor = makeAddress(0x61);
    const auto outdoor = makeAddress(0x62);

    registry.update(indoor, "Indoor", -40, makeReading(21.1F, 1), 1000);
    registry.update(outdoor, "Outdoor", -60, makeReading(4.2F, 1), 1000);

    assert(registry.assignRole(indoor, pumpsteer::ble::SensorRole::Indoor));
    assert(registry.assignRole(outdoor, pumpsteer::ble::SensorRole::Outdoor));

    const auto* selected_indoor = registry.selected(
        pumpsteer::ble::SensorRole::Indoor,
        5000,
        10000);
    assert(selected_indoor != nullptr);
    assert(std::fabs(selected_indoor->temperature_c - 21.1F) < 0.001F);

    assert(registry.selected(
        pumpsteer::ble::SensorRole::Indoor,
        20001,
        10000) == nullptr);
}

void testRoleIsUnique() {
    pumpsteer::ble::SensorRegistry registry;
    const auto first = makeAddress(0x63);
    const auto second = makeAddress(0x64);

    registry.update(first, "First", -40, makeReading(20.0F, 1), 1000);
    registry.update(second, "Second", -40, makeReading(20.5F, 1), 1000);

    assert(registry.assignRole(first, pumpsteer::ble::SensorRole::Indoor));
    assert(registry.assignRole(second, pumpsteer::ble::SensorRole::Indoor));

    assert(registry.find(first)->role == pumpsteer::ble::SensorRole::Unassigned);
    assert(registry.find(second)->role == pumpsteer::ble::SensorRole::Indoor);
}

}  // namespace

int main() {
    testDiscoveryAndDuplicateHandling();
    testRoleAssignmentAndFreshness();
    testRoleIsUnique();

    std::cout << "PumpSteer Mini sensor registry tests passed\n";
    return 0;
}
