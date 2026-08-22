# Changelog

All notable changes to PumpSteer Mini will be documented in this file.

The project is currently pre-alpha. Version numbers may change before the first public firmware release.

## Unreleased

### Added

- ESP-IDF project skeleton for ESP32-S3.
- Hardware-independent PumpSteer Core.
- PI controller with anti-windup and frozen integral during braking.
- Safe mode and bypass request.
- Aggressiveness levels 0-5 and comfort-floor behavior.
- Brake ramp with capped control-step time.
- Pre-brake and forecast-gated preheat hooks.
- Precooling mode represented in the public core API.
- BTHome v2 decoder.
- Shelly BLU H&T decoding for temperature, humidity, battery and packet ID.
- ESP-NimBLE passive scanner.
- BLE sensor registry with freshness tracking and indoor/outdoor role assignment.
- Host-side tests for control core, BTHome and BLE registry.
- Initial architecture, roadmap and design-decision documents.
- Passive thermal-learning component scaffold with bounded, explainable model state.

### Planned next

- Persist sensor assignments and device configuration in NVS.
- Wi-Fi provisioning and local web UI.
- Ohmonwifiplus local API output.
- Electricity-price provider.
- Weather provider.
- Full precooling strategy.
- Optional MQTT/Home Assistant Discovery.
- OTA and production watchdog behavior.
