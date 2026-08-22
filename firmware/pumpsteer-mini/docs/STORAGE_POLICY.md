# Storage policy

Persist only compact durable state:
- configuration
- sensor assignments
- schema version
- compact learned-model parameters

Avoid high-frequency raw telemetry writes to flash. Use RAM and optional MQTT telemetry for detailed runtime observations.
