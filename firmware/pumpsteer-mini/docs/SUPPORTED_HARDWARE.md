# Supported hardware

## Reference controller

- ESP32-S3-WROOM-1-N16R8 development board
- 16 MB flash
- 8 MB PSRAM

## BLE sensors

Initial first-class support:
- Shelly BLU H&T using BTHome v2 advertisements

Additional BTHome temperature sensors may be added when their payload behavior is verified.

## Heat-pump output

Initial output target:
- Ohmonwifiplus over the local network

PumpSteer Mini does not directly emulate the heat-pump outdoor-temperature sensor in the initial hardware architecture.
