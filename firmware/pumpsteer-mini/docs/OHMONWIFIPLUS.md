# Ohmonwifiplus integration notes

PumpSteer Mini will use Ohmonwifiplus as the first output adapter.

The output component must implement:
- connection health
- validated temperature range
- output rounding
- hysteresis/deadband
- minimum update interval
- bypass command/support where available
- explicit error reporting

The control core must never make HTTP calls directly.

Before production use, verify the exact local API behavior and the safe bypass behavior against the installed Ohmonwifiplus firmware.
