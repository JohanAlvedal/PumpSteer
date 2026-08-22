# Control contract

The hardware-independent control core receives validated, normalized inputs and returns a bounded requested output plus diagnostics.

Platform components are responsible for collecting/validating input data and applying the requested output safely.

The core must not directly access BLE, Wi-Fi, HTTP, MQTT, NVS, Home Assistant or Ohmonwifiplus.
