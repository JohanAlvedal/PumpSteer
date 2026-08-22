#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "pumpsteer/bthome.h"

namespace pumpsteer::ble {

enum class SensorRole : std::uint8_t {
    Unassigned,
    Indoor,
    Outdoor,
};

struct SensorAddress {
    std::array<std::uint8_t, 6> bytes{};
    std::uint8_t type = 0;

    bool operator==(const SensorAddress& other) const {
        return type == other.type && bytes == other.bytes;
    }
};

struct SensorRecord {
    bool occupied = false;
    SensorAddress address{};
    std::array<char, 32> name{};
    SensorRole role = SensorRole::Unassigned;

    float temperature_c = 0.0F;
    float humidity_percent = 0.0F;
    std::uint8_t battery_percent = 0;
    int rssi = 0;

    bool has_temperature = false;
    bool has_humidity = false;
    bool has_battery = false;
    bool has_packet_id = false;
    std::uint8_t packet_id = 0;

    std::uint64_t last_seen_ms = 0;
};

enum class RegistryUpdate : std::uint8_t {
    Added,
    Updated,
    SeenDuplicate,
    IgnoredNoTemperature,
    Full,
};

class SensorRegistry {
public:
    static constexpr std::size_t kMaxSensors = 16;

    RegistryUpdate update(
        const SensorAddress& address,
        const char* name,
        int rssi,
        const bthome::Reading& reading,
        std::uint64_t now_ms);

    std::size_t count() const;
    const SensorRecord* at(std::size_t index) const;
    const SensorRecord* find(const SensorAddress& address) const;

    bool assignRole(const SensorAddress& address, SensorRole role);
    const SensorRecord* selected(
        SensorRole role,
        std::uint64_t now_ms,
        std::uint64_t max_age_ms) const;

    static bool isFresh(
        const SensorRecord& sensor,
        std::uint64_t now_ms,
        std::uint64_t max_age_ms);

private:
    SensorRecord* findMutable(const SensorAddress& address);
    SensorRecord* allocate(const SensorAddress& address);
    static void copyName(std::array<char, 32>& destination, const char* source);
    static void applyReading(SensorRecord& sensor, const bthome::Reading& reading);

    std::array<SensorRecord, kMaxSensors> sensors_{};
    std::size_t count_ = 0;
};

}  // namespace pumpsteer::ble
