# PumpSteer Mini

PumpSteer Mini is a standalone ESP32-S3 firmware for local heat-pump optimization by calculating a virtual outdoor temperature and sending it to Ohmonwifiplus.

The ESP32 is the controller. Home Assistant and MQTT are optional.

## Reference development hardware

- ESP32-S3-WROOM-1-N16R8 development board
- 16 MB flash
- 8 MB PSRAM

## Planned capabilities

- BLE indoor and outdoor temperature sensors
- Shelly BLU H&T / BTHome support
- local PI temperature control
- electricity-price optimization
- six-hour price lookahead
- weather forecast lookahead
- preheat
- pre-brake and brake
- precool for verified cooling installations
- aggressiveness 0-5
- Ohmonwifiplus local output
- local setup/status web UI
- optional MQTT and Home Assistant Discovery
- passive, explainable thermal learning
- OTA updates and production failsafes

## Design principles

- PI control is the primary feedback loop.
- Price and forecast are bounded overlays.
- The PI integral is frozen while braking.
- Comfort limits take priority over price optimization.
- Missing internet data degrades to local control.
- Stale required local temperature data leads to safe behavior.
- Home Assistant is never required for control.
- Learning estimates the building, not the control algorithm.
- Learning starts passive and may only influence control later within hard bounds.

See [ARCHITECTURE.md](ARCHITECTURE.md), [ROADMAP.md](ROADMAP.md) and [DECISIONS.md](DECISIONS.md).

## Current milestone

Implemented:

- ESP-IDF project skeleton for ESP32-S3-WROOM-1-N16R8
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
- precooling represented in the public API
- BTHome v2 service-data decoder
- Shelly BLU H&T temperature, humidity, battery and packet-ID decoding
- passive ESP-NimBLE BTHome discovery
- fixed-size BLE sensor registry without heap allocation
- indoor/outdoor sensor roles with freshness tracking
- explicit rejection of encrypted BTHome until key support is implemented
- passive thermal-learning component with heat-loss estimate and confidence
- host-side tests

Next:

1. persist indoor/outdoor BLE assignment and configuration in NVS
2. Wi-Fi provisioning and local configuration UI/API
3. Ohmonwifiplus local API client
4. electricity-price provider
5. weather forecast provider
6. connect live inputs to the control loop
7. complete and validate precool strategy
8. optional MQTT and Home Assistant Discovery
9. OTA and production watchdog behavior

## BLE behavior

PumpSteer Mini scans passively for 16-bit BTHome service data with UUID `0xFCD2`.
Duplicate filtering is intentionally disabled because sensors advertise updated measurements periodically from the same BLE address.

The registry currently supports up to 16 discovered temperature sensors and enforces one Indoor role and one Outdoor role.

## Thermal learning

The initial learner is deliberately passive. It can estimate a simple heat-loss coefficient from qualified reduced-heating observation windows, track sample count/confidence and predict an expected temperature drop for diagnostics.

It is not yet connected to control output and it cannot modify PI gains, target temperature, aggressiveness or comfort limits.

## ESP-IDF build

```bash
idf.py set-target esp32s3
idf.py build
```

While the project is still stored inside the original PumpSteer repository, run these commands from `firmware/pumpsteer-mini/`. After migration to `PumpSteer-Mini`, run them from the repository root.

## Host tests

```bash
cd host_tests
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

## Repository migration

The project is temporarily developed in `JohanAlvedal/PumpSteer` on branch `mini-development` under `firmware/pumpsteer-mini/`.

See [MOVE_TO_NEW_REPO.md](MOVE_TO_NEW_REPO.md) before moving it to `JohanAlvedal/PumpSteer-Mini`.

No source files should be removed from the original repository until the standalone repository has been verified.
