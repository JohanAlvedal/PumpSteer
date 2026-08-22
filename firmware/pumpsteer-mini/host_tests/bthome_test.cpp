#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>

#include "pumpsteer/bthome.h"

namespace {

void testShellyBluHtPacket() {
    const std::uint8_t payload[] = {
        0x40,
        0x00, 0x05,
        0x01, 0x5E,
        0x2E, 0x37,
        0x45, 0xD7, 0x00,
    };

    pumpsteer::bthome::Reading reading;
    const auto status = pumpsteer::bthome::decodeServiceData(
        payload,
        sizeof(payload),
        reading);

    assert(status == pumpsteer::bthome::DecodeStatus::Ok);
    assert(reading.version == 2);
    assert(!reading.encrypted);
    assert(reading.has_packet_id && reading.packet_id == 5);
    assert(reading.has_battery && reading.battery_percent == 94);
    assert(reading.has_humidity && std::fabs(reading.humidity_percent - 55.0F) < 0.001F);
    assert(reading.has_temperature && std::fabs(reading.temperature_c - 21.5F) < 0.001F);
}

void testNegativeTemperature() {
    const std::uint8_t payload[] = {
        0x40,
        0x45, 0xF1, 0xFF,
    };

    pumpsteer::bthome::Reading reading;
    const auto status = pumpsteer::bthome::decodeServiceData(
        payload,
        sizeof(payload),
        reading);

    assert(status == pumpsteer::bthome::DecodeStatus::Ok);
    assert(reading.has_temperature);
    assert(std::fabs(reading.temperature_c - (-1.5F)) < 0.001F);
}

void testEncryptedPacketIsRejectedUntilKeySupportExists() {
    const std::uint8_t payload[] = {0x41, 0xAA, 0xBB};

    pumpsteer::bthome::Reading reading;
    const auto status = pumpsteer::bthome::decodeServiceData(
        payload,
        sizeof(payload),
        reading);

    assert(status == pumpsteer::bthome::DecodeStatus::EncryptedUnsupported);
    assert(reading.encrypted);
}

void testTruncatedTemperatureIsRejected() {
    const std::uint8_t payload[] = {0x40, 0x45, 0x10};

    pumpsteer::bthome::Reading reading;
    const auto status = pumpsteer::bthome::decodeServiceData(
        payload,
        sizeof(payload),
        reading);

    assert(status == pumpsteer::bthome::DecodeStatus::MalformedPayload);
}

}  // namespace

int main() {
    testShellyBluHtPacket();
    testNegativeTemperature();
    testEncryptedPacketIsRejectedUntilKeySupportExists();
    testTruncatedTemperatureIsRejected();

    std::cout << "PumpSteer Mini BTHome tests passed\n";
    return 0;
}
