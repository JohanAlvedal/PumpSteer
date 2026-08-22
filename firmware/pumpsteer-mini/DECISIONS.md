# PumpSteer Mini Design Decisions

This document records decisions that should not be casually changed while implementing the firmware.

## Standalone first

**Decision:** PumpSteer Mini must work without Home Assistant, MQTT, Raspberry Pi or another local server.

**Reason:** The ESP32 is the controller. External systems are optional interfaces and data sources only.

## ESP-IDF and C++

**Decision:** Use ESP-IDF with C++ for production firmware.

**Reason:** PumpSteer Mini needs deterministic local control, BLE/Wi-Fi coexistence, NVS, OTA, watchdogs, HTTPS and long-term maintainability. The control core remains standard C++ so it can be unit-tested on a desktop.

## Reference hardware

**Decision:** Develop against ESP32-S3-WROOM-1-N16R8.

**Reason:** 16 MB flash and 8 MB PSRAM provide ample margin for HTTPS, JSON, BLE, local web UI, OTA and future features without forcing early memory optimization.

## PI remains the controller

**Decision:** The PI controller is the only primary comfort feedback loop.

**Reason:** Price, weather and learned thermal estimates should influence strategy without creating competing feedback loops.

## Freeze the integral while braking

**Decision:** Hold the PI integral constant while braking.

**Reason:** The integral preserves the pre-brake heating context and prevents unnecessary recovery lag after an expensive period.

## Price and weather are overlays

**Decision:** Price and forecast logic must be bounded overlays on the PI result.

**Reason:** This keeps behavior explainable and allows graceful degradation when internet data disappears.

## BLE for real local temperatures

**Decision:** Prefer BLE sensors for indoor and real outdoor temperature.

**Reason:** Local measurements should not depend on cloud services or Home Assistant. Shelly BLU H&T/BTHome is a first-class starting point.

## Local outdoor temperature beats forecast current temperature

**Decision:** Forecast services are for anticipation. A valid local outdoor BLE sensor remains the preferred current outdoor measurement.

**Reason:** Forecast-grid current temperature can differ materially from the temperature at the actual building.

## Stale sensor data is not valid data

**Decision:** Every temperature reading carries freshness metadata.

**Reason:** Reusing a last-known BLE temperature indefinitely is unsafe. Required stale inputs lead to a safe state or an explicitly configured fallback.

## Ohmonwifiplus is the output adapter

**Decision:** PumpSteer Mini calculates temperature; Ohmonwifiplus performs the physical sensor emulation/bypass function.

**Reason:** Reusing Ohmonwifiplus avoids duplicating safety-critical resistor/sensor-emulation hardware in the first PumpSteer Mini hardware design.

## MQTT is optional

**Decision:** MQTT and Home Assistant Discovery are optional.

**Reason:** Home Assistant should provide visibility and control convenience, not runtime dependency.

## Precooling is separate from summer passthrough

**Decision:** Reserve explicit cooling/precooling modes and capabilities from the beginning.

**Reason:** Heating and active cooling cannot safely be assumed to have identical fake-temperature semantics. Precooling will only be activated after the output behavior has been verified.

## Learning learns the building, not the algorithm

**Decision:** Self-learning estimates building response parameters only.

It may learn or estimate:
- heat-loss coefficient
- response delay
- heating response
- cooling response
- confidence

It may not autonomously modify:
- PI Kp/Ki
- target temperature
- aggressiveness
- comfort floor/ceiling
- hard safety bounds

**Reason:** The controller must remain explainable and predictable.

## Learning is passive-first

**Decision:** New learned values initially run in observation/shadow mode.

**Reason:** We must compare predictions against real outcomes before learned data is allowed to affect control.

## Learning influence is bounded

**Decision:** When activated in a later milestone, learning may only adjust timing/strength within explicit hard bounds.

**Reason:** Bad samples, unusual weather or sensor faults must not be able to destabilize the controller.

## Do not continuously write raw telemetry to NVS

**Decision:** Store compact model state and configuration only.

**Reason:** NVS is flash-backed. High-frequency raw logging would create unnecessary flash wear. Detailed telemetry should be streamed over MQTT or kept in RAM when needed.

## Provider abstraction for internet data

**Decision:** Electricity price and weather APIs are accessed through provider interfaces.

**Reason:** External APIs change. Provider isolation prevents changes in external services from spreading into the control core.

## No deletion from the original PumpSteer repository until migration is verified

**Decision:** The temporary `firmware/pumpsteer-mini` copy remains intact until the standalone `PumpSteer-Mini` repository has been populated and verified.

**Reason:** The current branch is the migration safety copy.
