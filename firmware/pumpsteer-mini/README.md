# PumpSteer Mini firmware

PumpSteer Mini is a standalone ESP32-S3 firmware for local heat-pump optimization.
The ESP32 is the controller. Home Assistant is optional and will later be exposed through MQTT discovery.

## Reference development hardware

- ESP32-S3-WROOM-1-N16R8 development board
- 16 MB flash
- 8 MB PSRAM

## Architecture

The firmware is split into a hardware-independent control core and platform providers.
The core follows the same high-level PumpSteer principles as the Home Assistant integration:

- PI control is the primary feedback loop.
- Price and forecast are bounded overlays.
- The PI integral is frozen while braking.
- Comfort limits take priority over price optimization.
- Missing indoor/outdoor data requests a safe bypass.
- Missing internet price data degrades to local PI control instead of stopping heating control.

Precooling is represented in the public control API from the start, but it is intentionally not activated yet.
The correct output behavior must be verified against Ohmonwifiplus and heat-pump cooling semantics first.

## Current milestone

Implemented:

- ESP-IDF project skeleton
- hardware-independent C++ control core
- PI controller with anti-windup
- safe mode / bypass request
- summer passthrough
- aggressiveness 0 pure PI mode
- comfort floor
- brake ramp with 60-second dt cap
- expensive-price braking
- pre-brake hook
- forecast-gated preheat hook
- BTHome v2 service-data decoder
- Shelly BLU H&T temperature, humidity, battery and packet-id decoding
- explicit rejection of encrypted BTHome until key support is implemented
- host-side core and BTHome tests

Next:

1. ESP32 NimBLE scanner and Shelly BLU H&T discovery
2. indoor/outdoor BLE sensor assignment and freshness tracking
3. Wi-Fi provisioning and NVS configuration
4. Ohmonwifiplus local API client
5. electricity price provider
6. weather forecast provider
7. precool strategy
8. optional MQTT and Home Assistant discovery
9. OTA and production watchdog behavior

## ESP-IDF build

```bash
cd firmware/pumpsteer-mini
idf.py set-target esp32s3
idf.py build
```

## Host tests

```bash
cd firmware/pumpsteer-mini/host_tests
cmake -S . -B build
cmake --build build
./build/pumpsteer_mini_core_test
./build/pumpsteer_mini_bthome_test
```
