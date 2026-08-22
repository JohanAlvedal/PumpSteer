# Configuration schema notes

PumpSteer Mini configuration will be stored in NVS with an explicit schema version.

Planned durable fields include:
- schema version
- Wi-Fi provisioning state
- location/coordinates
- electricity area
- selected indoor BLE sensor identity
- selected outdoor BLE sensor identity
- Ohmonwifiplus address/settings
- target temperature
- aggressiveness
- holiday settings
- optional MQTT settings
- thermal-model state

Credentials must never be logged in plaintext.

Configuration migrations must be forward-only and preserve a safe factory-reset path.
