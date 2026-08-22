#pragma once

#include "esp_err.h"

#include "pumpsteer/sensor_registry.h"

struct ble_gap_disc_desc;
struct ble_gap_event;

namespace pumpsteer::ble {

class BleScanner {
public:
    explicit BleScanner(SensorRegistry& registry);

    esp_err_t start();

private:
    static void hostTask(void* parameter);
    static void onSync();
    static void onReset(int reason);
    static int gapEvent(ble_gap_event* event, void* argument);

    esp_err_t startScan();
    void handleAdvertisement(const ble_gap_disc_desc& advertisement);

    static BleScanner* instance_;
    SensorRegistry& registry_;
};

}  // namespace pumpsteer::ble
