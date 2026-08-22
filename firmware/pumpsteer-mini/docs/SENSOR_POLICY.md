# Sensor policy

PumpSteer Mini treats sensor identity, freshness and plausibility as part of safety.

- Indoor and outdoor roles are explicit.
- One device can occupy each role.
- A stale reading is invalid even if a numeric value is still cached.
- Implausible values are rejected before reaching the control core.
- Shelly BLU H&T over BTHome v2 is the first-class reference sensor.
