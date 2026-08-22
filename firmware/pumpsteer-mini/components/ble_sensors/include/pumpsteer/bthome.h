#pragma once

#include <cstddef>
#include <cstdint>

namespace pumpsteer::bthome {

enum class DecodeStatus : std::uint8_t {
    Ok,
    InvalidArgument,
    UnsupportedVersion,
    EncryptedUnsupported,
    UnsupportedObject,
    MalformedPayload,
};

struct Reading {
    bool encrypted = false;
    bool trigger_based = false;
    std::uint8_t version = 0;

    bool has_packet_id = false;
    std::uint8_t packet_id = 0;

    bool has_battery = false;
    std::uint8_t battery_percent = 0;

    bool has_humidity = false;
    float humidity_percent = 0.0F;

    bool has_temperature = false;
    float temperature_c = 0.0F;

    bool has_button = false;
    std::uint8_t button_event = 0;

    bool has_device_type = false;
    std::uint16_t device_type = 0;
};

DecodeStatus decodeServiceData(
    const std::uint8_t* payload,
    std::size_t payload_size,
    Reading& reading);

}  // namespace pumpsteer::bthome
