# API/provider policy

External electricity-price and weather services are implementation details behind provider interfaces.

Provider code must:
- normalize external data before it reaches the control core
- validate ranges and timestamps
- mark stale/missing data explicitly
- cache only what is required for safe local operation
- avoid placing service-specific assumptions in PumpSteer Core

If a provider disappears or changes format, replacing that provider must not require redesigning the controller.
