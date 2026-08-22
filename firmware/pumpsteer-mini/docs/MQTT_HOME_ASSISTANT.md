# Home Assistant / MQTT contract notes

MQTT is optional and must not be required for runtime control.

Planned Home Assistant entities include:
- indoor temperature
- outdoor temperature
- PumpSteer/fake outdoor temperature
- current price
- price class
- operating mode
- brake/preheat/precool state
- BLE battery/RSSI
- Ohmonwifiplus status
- learning confidence and learned heat-loss estimate
- target temperature control
- aggressiveness control
- holiday mode
- enable/disable control
- force bypass
- reset learned model

PumpSteer Mini remains the source of truth and persists accepted configuration locally.
