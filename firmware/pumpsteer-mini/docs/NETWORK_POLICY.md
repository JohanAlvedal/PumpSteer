# Network policy

The controller must remain safe when the network is partially available.

- Local BLE + PI control should not depend on internet reachability.
- Price/weather HTTPS clients must have bounded timeouts and retries.
- Ohmonwifiplus local communication is independent from cloud services.
- MQTT is optional and isolated from control.
- Provisioning must not expose stored credentials through logs or diagnostics.
