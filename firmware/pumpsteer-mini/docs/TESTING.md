# Testing strategy

PumpSteer Mini separates hardware-independent logic from ESP32 platform code so the most safety-relevant decisions can be tested without hardware.

## Host tests

Required for:
- PI behavior
- state-machine decisions
- price/forecast strategy helpers
- BTHome parsing
- BLE registry behavior
- thermal-learning math
- future output clamping and configuration validation where practical

## Hardware tests

Required for:
- ESP-NimBLE scanning
- Wi-Fi/BLE coexistence
- NVS persistence
- provisioning
- Ohmonwifiplus communication
- watchdog/restart recovery
- OTA/rollback

## Fault injection

Before production release, explicitly test:
- indoor sensor disappears
- outdoor sensor disappears
- both BLE sensors disappear
- internet disappears
- stale prices
- stale forecast
- Ohmonwifiplus unreachable
- reboot during braking/preheat
- corrupted/invalid stored configuration
- unrealistic sensor values

Learning must be tested in shadow mode before any learned value can affect control.
