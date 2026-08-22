#include "pumpsteer/bthome.h"

namespace pumpsteer::bthome {

namespace {

constexpr std::uint8_t kEncryptionMask = 0x01;
constexpr std::uint8_t kTriggerBasedMask = 0x04;
constexpr std::uint8_t kVersionShift = 5;
constexpr std::uint8_t kVersionMask = 0x07;
constexpr std::uint8_t kSupportedVersion = 2;

bool hasBytes(
    const std::size_t index,
    const std::size_t bytes_needed,
    const std::size_t payload_size) {
    return index <= payload_size && bytes_needed <= payload_size - index;
}

std::uint16_t readLe16(const std::uint8_t* data) {
    return static_cast<std::uint16_t>(data[0]) |
        (static_cast<std::uint16_t>(data[1]) << 8U);
}

std::int16_t readLeS16(const std::uint8_t* data) {
    return static_cast<std::int16_t>(readLe16(data));
}

}  // namespace

DecodeStatus decodeServiceData(
    const std::uint8_t* payload,
    const std::size_t payload_size,
    Reading& reading) {
    reading = Reading{};

    if (payload == nullptr || payload_size == 0) {
        return DecodeStatus::InvalidArgument;
    }

    const std::uint8_t device_info = payload[0];
    reading.encrypted = (device_info & kEncryptionMask) != 0;
    reading.trigger_based = (device_info & kTriggerBasedMask) != 0;
    reading.version = (device_info >> kVersionShift) & kVersionMask;

    if (reading.version != kSupportedVersion) {
        return DecodeStatus::UnsupportedVersion;
    }

    if (reading.encrypted) {
        return DecodeStatus::EncryptedUnsupported;
    }

    std::size_t index = 1;
    while (index < payload_size) {
        const std::uint8_t object_id = payload[index++];

        switch (object_id) {
            case 0x00:  // Packet ID
                if (!hasBytes(index, 1, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                reading.has_packet_id = true;
                reading.packet_id = payload[index++];
                break;

            case 0x01:  // Battery, uint8, 1 %
                if (!hasBytes(index, 1, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                reading.has_battery = true;
                reading.battery_percent = payload[index++];
                break;

            case 0x2E:  // Humidity, uint8, 1 %
                if (!hasBytes(index, 1, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                reading.has_humidity = true;
                reading.humidity_percent = static_cast<float>(payload[index++]);
                break;

            case 0x3A:  // Button event, uint8
                if (!hasBytes(index, 1, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                reading.has_button = true;
                reading.button_event = payload[index++];
                break;

            case 0x45: {  // Temperature, sint16, 0.1 °C
                if (!hasBytes(index, 2, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                reading.has_temperature = true;
                reading.temperature_c = static_cast<float>(readLeS16(payload + index)) * 0.1F;
                index += 2;
                break;
            }

            case 0xF0:  // Device type ID, uint16
                if (!hasBytes(index, 2, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                reading.has_device_type = true;
                reading.device_type = readLe16(payload + index);
                index += 2;
                break;

            case 0xF1:  // Firmware version, uint32
                if (!hasBytes(index, 4, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                index += 4;
                break;

            case 0xF2:  // Firmware version, uint24
                if (!hasBytes(index, 3, payload_size)) {
                    return DecodeStatus::MalformedPayload;
                }
                index += 3;
                break;

            default:
                return DecodeStatus::UnsupportedObject;
        }
    }

    return DecodeStatus::Ok;
}

}  // namespace pumpsteer::bthome
