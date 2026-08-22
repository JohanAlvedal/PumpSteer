# Security Policy

PumpSteer Mini controls heating equipment through a local network output device. Treat safety-related changes conservatively.

## Reporting a vulnerability

Until a dedicated security contact/process is published, report security issues privately to the repository owner rather than opening a public issue containing exploit details or credentials.

## Safety-sensitive areas

Changes require extra care when they affect:

- safe mode or bypass behavior
- stale sensor handling
- Ohmonwifiplus output validation
- firmware update/rollback behavior
- network credential storage
- bounds on fake outdoor temperature
- learning influence on control decisions

Never include real Wi-Fi, MQTT or other credentials in logs, issues, test fixtures or commits.
