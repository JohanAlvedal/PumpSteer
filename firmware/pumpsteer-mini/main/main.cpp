#include "esp_log.h"
#include "esp_timer.h"

#include "pumpsteer/controller.h"

namespace {

constexpr char kTag[] = "pumpsteer_mini";
pumpsteer::Controller g_controller;

}  // namespace

extern "C" void app_main(void) {
    const auto now_ms = static_cast<std::uint64_t>(esp_timer_get_time() / 1000ULL);
    g_controller.reset(now_ms);

    ESP_LOGI(kTag, "PumpSteer Mini firmware bootstrap started");
    ESP_LOGI(kTag, "Core controller initialized; hardware providers are not connected yet");
}
