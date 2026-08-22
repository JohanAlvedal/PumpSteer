#include "pumpsteer/sensor_registry.h"

#include <algorithm>
#include <cstring>

namespace pumpsteer::ble {

RegistryUpdate SensorRegistry::update(
    const SensorAddress& address,
    const char* name,
    const int rssi,
    const bthome::Reading& reading,
    const std::uint64_t now_ms) {
    if (!reading.has_temperature) {
        return RegistryUpdate::IgnoredNoTemperature;
    }

    SensorRecord* sensor = findMutable(address);
    const bool is_new = sensor == nullptr;
    if (is_new) {
        sensor = allocate(address);
        if (sensor == nullptr) {
            return RegistryUpdate::Full;
        }
    }

    sensor->last_seen_ms = now_ms;
    sensor->rssi = rssi;
    copyName(sensor->name, name);

    if (!is_new && reading.has_packet_id && sensor->has_packet_id &&
        reading.packet_id == sensor->packet_id) {
        return RegistryUpdate::SeenDuplicate;
    }

    applyReading(*sensor, reading);
    return is_new ? RegistryUpdate::Added : RegistryUpdate::Updated;
}

std::size_t SensorRegistry::count() const {
    return count_;
}

const SensorRecord* SensorRegistry::at(const std::size_t index) const {
    if (index >= count_) {
        return nullptr;
    }
    return &sensors_[index];
}

const SensorRecord* SensorRegistry::find(const SensorAddress& address) const {
    for (std::size_t index = 0; index < count_; ++index) {
        if (sensors_[index].occupied && sensors_[index].address == address) {
            return &sensors_[index];
        }
    }
    return nullptr;
}

bool SensorRegistry::assignRole(const SensorAddress& address, const SensorRole role) {
    SensorRecord* target = findMutable(address);
    if (target == nullptr) {
        return false;
    }

    if (role != SensorRole::Unassigned) {
        for (std::size_t index = 0; index < count_; ++index) {
            if (&sensors_[index] != target && sensors_[index].role == role) {
                sensors_[index].role = SensorRole::Unassigned;
            }
        }
    }

    target->role = role;
    return true;
}

const SensorRecord* SensorRegistry::selected(
    const SensorRole role,
    const std::uint64_t now_ms,
    const std::uint64_t max_age_ms) const {
    if (role == SensorRole::Unassigned) {
        return nullptr;
    }

    for (std::size_t index = 0; index < count_; ++index) {
        const auto& sensor = sensors_[index];
        if (sensor.occupied && sensor.role == role && sensor.has_temperature &&
            isFresh(sensor, now_ms, max_age_ms)) {
            return &sensor;
        }
    }
    return nullptr;
}

bool SensorRegistry::isFresh(
    const SensorRecord& sensor,
    const std::uint64_t now_ms,
    const std::uint64_t max_age_ms) {
    if (!sensor.occupied || sensor.last_seen_ms == 0 || now_ms < sensor.last_seen_ms) {
        return false;
    }
    return now_ms - sensor.last_seen_ms <= max_age_ms;
}

SensorRecord* SensorRegistry::findMutable(const SensorAddress& address) {
    for (std::size_t index = 0; index < count_; ++index) {
        if (sensors_[index].occupied && sensors_[index].address == address) {
            return &sensors_[index];
        }
    }
    return nullptr;
}

SensorRecord* SensorRegistry::allocate(const SensorAddress& address) {
    if (count_ >= sensors_.size()) {
        return nullptr;
    }

    auto& sensor = sensors_[count_++];
    sensor = SensorRecord{};
    sensor.occupied = true;
    sensor.address = address;
    return &sensor;
}

void SensorRegistry::copyName(
    std::array<char, 32>& destination,
    const char* source) {
    destination.fill('\0');
    if (source == nullptr || source[0] == '\0') {
        constexpr char fallback[] = "BTHome sensor";
        std::copy_n(fallback, sizeof(fallback), destination.begin());
        return;
    }

    const std::size_t length = std::min(
        std::strlen(source),
        destination.size() - 1);
    std::copy_n(source, length, destination.begin());
}

void SensorRegistry::applyReading(
    SensorRecord& sensor,
    const bthome::Reading& reading) {
    if (reading.has_temperature) {
        sensor.has_temperature = true;
        sensor.temperature_c = reading.temperature_c;
    }
    if (reading.has_humidity) {
        sensor.has_humidity = true;
        sensor.humidity_percent = reading.humidity_percent;
    }
    if (reading.has_battery) {
        sensor.has_battery = true;
        sensor.battery_percent = reading.battery_percent;
    }
    if (reading.has_packet_id) {
        sensor.has_packet_id = true;
        sensor.packet_id = reading.packet_id;
    }
}

}  // namespace pumpsteer::ble
