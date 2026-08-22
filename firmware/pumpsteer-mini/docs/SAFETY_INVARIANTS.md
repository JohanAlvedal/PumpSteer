# Safety invariants

These invariants are intended to become testable requirements as the firmware matures.

- Fake outdoor temperature must always remain within configured hard bounds.
- Stale required local temperature data must never be treated as current.
- Price optimization must never override the configured comfort boundary.
- Missing price data must disable price-dependent optimization rather than invent a price state.
- Missing forecast data must disable forecast-dependent preheat/precool rather than invent a forecast.
- Learning output must not directly modify hard safety bounds.
- Learning output must not automatically change PI gains, target temperature or aggressiveness.
- MQTT/Home Assistant loss must not stop the standalone controller.
- Restart recovery must return to a deterministic safe state before normal output resumes.
