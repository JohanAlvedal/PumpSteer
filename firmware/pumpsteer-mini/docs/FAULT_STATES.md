# Fault-state policy

PumpSteer Mini should report faults explicitly and degrade only the affected feature when possible.

Examples:
- MQTT unavailable -> local control continues
- Home Assistant unavailable -> local control continues
- forecast unavailable -> no forecast-dependent preheat/precool
- price unavailable -> no price-dependent optimization
- indoor temperature stale -> safe mode/bypass request
- outdoor temperature stale with no valid fallback -> safe mode/bypass request
- Ohmonwifiplus unavailable -> output fault and safe handling
