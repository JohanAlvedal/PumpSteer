# Contributing to PumpSteer Mini

PumpSteer Mini is currently in early development. Keep changes small, testable and consistent with the documented architecture.

## Development rules

- Do not bypass the hardware-independent control core with hidden control logic in network, BLE, web or MQTT components.
- Keep price and forecast providers separate from the control algorithm.
- Preserve safe degradation when external data is missing.
- Keep learning passive-first, explainable and bounded.
- Add or update host tests for hardware-independent behavior.
- Keep code comments in English.
- Never commit credentials, Wi-Fi passwords, MQTT passwords or API secrets.

## Before submitting a change

```bash
cd host_tests
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

For firmware changes, also verify an ESP32-S3 build with ESP-IDF.

## Control behavior changes

Changes to PI behavior, braking, preheat, precool, comfort limits, safety behavior or learning influence should include:

- a short rationale
- unit tests or test vectors
- an update to `DECISIONS.md` when a new long-term design decision is introduced
- an update to `ROADMAP.md` when milestone scope changes
