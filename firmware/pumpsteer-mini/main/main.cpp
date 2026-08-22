#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"

#include "pumpsteer/ble_scanner.h"
#include "pumpsteer/controller.h"
#include "pumpsteer/sensor_registry.h"

namespace {

constexpr char kTag[] = "pumpsteer_mini";
pumpsteer::Controller g_controller;
pumpsteer::ble::SensorRegistry g_sensor_registry;
pumpsteer::ble::BleScanner g_ble_scanner(g_sensor_registry);

esp_err_t initializeNvs() {
    esp_err_t result = nvs_flash_init();
    if (result == ESP_ERR_NVS_NO_FREE_PAGES || result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        result = nvs_flash_init();
    }
    return result;
}

}  // namespace

extern "C" void app_main(void) {
    ESP_ERROR_CHECK(initializeNvs());

    const auto now_ms = static_cast<std::uint64_t>(esp_timer_get_time() / 1000ULL);
    g_controller.reset(now_ms);

    ESP_LOGI(kTag, "PumpSteer Mini firmware bootstrap started");
    ESP_LOGI(kTag, "Starting passive BTHome discovery for temperature sensors");

    const esp_err_t ble_result = g_ble_scanner.start();
    if (ble_result != ESP_OK) {
        ESP_LOGE(kTag, "BLE startup failed: %s", esp_err_to_name(ble_result));
        return;
    }

    ESP_LOGI(kTag, "PumpSteer core initialized; BLE sensor discovery is active");
    ESP_LOGI(kTag, "Sensor assignment, Wi-Fi, Ohmigo and internet providers are not connected yet");
}
