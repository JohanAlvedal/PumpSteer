#include "pumpsteer/ble_scanner.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>

#include "esp_log.h"
#include "esp_timer.h"
#include "host/ble_gap.h"
#include "host/ble_hs.h"
#include "host/ble_hs_adv.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"

#include "pumpsteer/bthome.h"

namespace pumpsteer::ble {

namespace {

constexpr char kTag[] = "pumpsteer_ble";

std::array<char, 18> formatAddress(const SensorAddress& address) {
    std::array<char, 18> text{};
    std::snprintf(
        text.data(),
        text.size(),
        "%02X:%02X:%02X:%02X:%02X:%02X",
        address.bytes[5],
        address.bytes[4],
        address.bytes[3],
        address.bytes[2],
        address.bytes[1],
        address.bytes[0]);
    return text;
}

std::array<char, 32> copyAdvertisementName(const ble_hs_adv_fields& fields) {
    std::array<char, 32> name{};
    if (fields.name == nullptr || fields.name_len == 0) {
        return name;
    }

    const auto length = std::min<std::size_t>(fields.name_len, name.size() - 1);
    std::copy_n(reinterpret_cast<const char*>(fields.name), length, name.begin());
    return name;
}

}  // namespace

BleScanner* BleScanner::instance_ = nullptr;

BleScanner::BleScanner(SensorRegistry& registry) : registry_(registry) {}

esp_err_t BleScanner::start() {
    if (instance_ != nullptr && instance_ != this) {
        return ESP_ERR_INVALID_STATE;
    }

    instance_ = this;

    const esp_err_t result = nimble_port_init();
    if (result != ESP_OK) {
        ESP_LOGE(kTag, "Failed to initialize NimBLE: %s", esp_err_to_name(result));
        instance_ = nullptr;
        return result;
    }

    ble_hs_cfg.reset_cb = &BleScanner::onReset;
    ble_hs_cfg.sync_cb = &BleScanner::onSync;

    nimble_port_freertos_init(&BleScanner::hostTask);
    ESP_LOGI(kTag, "NimBLE host started; waiting for sync");
    return ESP_OK;
}

void BleScanner::hostTask(void*) {
    ESP_LOGI(kTag, "NimBLE host task running");
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void BleScanner::onSync() {
    if (instance_ == nullptr) {
        return;
    }

    const int address_result = ble_hs_util_ensure_addr(0);
    if (address_result != 0) {
        ESP_LOGE(kTag, "No usable BLE identity address; rc=%d", address_result);
        return;
    }

    const esp_err_t result = instance_->startScan();
    if (result != ESP_OK) {
        ESP_LOGE(kTag, "Could not start BLE scan: %s", esp_err_to_name(result));
    }
}

void BleScanner::onReset(const int reason) {
    ESP_LOGW(kTag, "NimBLE host reset; reason=%d", reason);
}

int BleScanner::gapEvent(ble_gap_event* event, void*) {
    if (instance_ == nullptr || event == nullptr) {
        return 0;
    }

    switch (event->type) {
        case BLE_GAP_EVENT_DISC:
            instance_->handleAdvertisement(event->disc);
            break;

        case BLE_GAP_EVENT_DISC_COMPLETE:
            ESP_LOGW(kTag, "BLE discovery stopped; reason=%d, restarting", event->disc_complete.reason);
            instance_->startScan();
            break;

        default:
            break;
    }

    return 0;
}

esp_err_t BleScanner::startScan() {
    std::uint8_t own_address_type = 0;
    const int address_result = ble_hs_id_infer_auto(0, &own_address_type);
    if (address_result != 0) {
        ESP_LOGE(kTag, "Failed to infer BLE address type; rc=%d", address_result);
        return ESP_FAIL;
    }

    ble_gap_disc_params parameters{};

    // Keep duplicate filtering disabled because BTHome sensors advertise updated
    // measurements periodically from the same BLE address.
    parameters.filter_duplicates = 0;
    parameters.passive = 1;
    parameters.itvl = 0;
    parameters.window = 0;
    parameters.filter_policy = 0;
    parameters.limited = 0;

    const int result = ble_gap_disc(
        own_address_type,
        BLE_HS_FOREVER,
        &parameters,
        &BleScanner::gapEvent,
        nullptr);
    if (result != 0) {
        ESP_LOGE(kTag, "Failed to start passive BLE discovery; rc=%d", result);
        return ESP_FAIL;
    }

    ESP_LOGI(kTag, "Passive BLE discovery started");
    return ESP_OK;
}

void BleScanner::handleAdvertisement(const ble_gap_disc_desc& advertisement) {
    ble_hs_adv_fields fields{};
    const int parse_result = ble_hs_adv_parse_fields(
        &fields,
        advertisement.data,
        advertisement.length_data);
    if (parse_result != 0 || fields.svc_data_uuid16 == nullptr ||
        fields.svc_data_uuid16_len < 3) {
        return;
    }

    const auto* service_data = fields.svc_data_uuid16;
    const std::uint16_t service_uuid =
        static_cast<std::uint16_t>(service_data[0]) |
        (static_cast<std::uint16_t>(service_data[1]) << 8U);
    if (service_uuid != bthome::kServiceUuid) {
        return;
    }

    bthome::Reading reading{};
    const auto decode_status = bthome::decodeServiceData(
        service_data + 2,
        fields.svc_data_uuid16_len - 2,
        reading);
    if (decode_status != bthome::DecodeStatus::Ok) {
        if (decode_status == bthome::DecodeStatus::EncryptedUnsupported) {
            ESP_LOGD(kTag, "Ignoring encrypted BTHome advertisement until key support is available");
        }
        return;
    }

    SensorAddress address{};
    std::copy_n(advertisement.addr.val, address.bytes.size(), address.bytes.begin());
    address.type = advertisement.addr.type;

    const auto name = copyAdvertisementName(fields);
    const auto now_ms = static_cast<std::uint64_t>(esp_timer_get_time() / 1000ULL);
    const auto update = registry_.update(
        address,
        name.data(),
        advertisement.rssi,
        reading,
        now_ms);

    if (update != RegistryUpdate::Added && update != RegistryUpdate::Updated) {
        return;
    }

    const auto address_text = formatAddress(address);
    const SensorRecord* sensor = registry_.find(address);
    if (sensor == nullptr) {
        return;
    }

    ESP_LOGI(
        kTag,
        "%s BTHome sensor %s (%s): %.1f C, humidity=%s, battery=%s, RSSI=%d",
        update == RegistryUpdate::Added ? "Discovered" : "Updated",
        address_text.data(),
        sensor->name.data(),
        sensor->temperature_c,
        sensor->has_humidity ? "available" : "n/a",
        sensor->has_battery ? "available" : "n/a",
        sensor->rssi);
}

}  // namespace pumpsteer::ble
