# PumpSteer Mini Architecture

## Overview

PumpSteer Mini is a standalone ESP32-S3 firmware that optimizes a heat pump by calculating a virtual outdoor temperature and sending it to Ohmonwifiplus over the local network.

Home Assistant is optional. The ESP32 is always the controller.

```text
BLE indoor ─┐
BLE outdoor ├────> PumpSteer Mini ─────> Ohmonwifiplus ─────> Heat pump
             │          │
Internet price ─────────┤
Internet forecast ──────┤
                        │
                        └──── optional MQTT / Home Assistant
```

## Core principle

The PI controller is the primary feedback loop. Price and weather are bounded overlays. Passive learning may provide predictions and bounded timing advice later, but it is not a replacement control loop.

## Major components

### `pumpsteer_core`

Hardware-independent control logic.

Inputs include:
- indoor temperature
- outdoor temperature
- target temperature
- aggressiveness
- current/future price classification
- weather outlook
- control capabilities

Outputs include:
- requested fake outdoor temperature
- operating mode
- brake/preheat/precool state
- bypass request
- diagnostic terms

The core must not depend on Wi-Fi, BLE, MQTT, HTTP, NVS, Home Assistant or Ohmonwifiplus.

### `ble_sensors`

Responsible for:
- passive BLE scanning
- BTHome v2 decoding
- Shelly BLU H&T support
- sensor registry
- RSSI and freshness
- indoor/outdoor sensor assignment

Local BLE outdoor temperature is the preferred real outdoor measurement. Weather-provider current temperature is only a fallback policy to be implemented explicitly.

### `thermal_learning`

Passive and explainable building-model estimation.

Initial model:
- heat-loss coefficient
- number of accepted samples
- confidence

Future model additions may include:
- response delay
- heating response
- cooling response

The learner must not modify PI gains, target temperature, aggressiveness or comfort limits automatically.

### `config`

Planned responsibilities:
- NVS-backed configuration
- schema versioning
- selected indoor/outdoor BLE sensors
- Wi-Fi settings
- location and electricity area
- Ohmonwifiplus settings
- optional MQTT settings

### `price`

Provider-based internet price retrieval. Providers normalize external data into internal price slots. The core never knows which external API is used.

### `weather`

Provider-based forecast retrieval. Providers normalize forecast data into internal forecast points. The core never knows which external API is used.

### `ohmigo`

Local output adapter for Ohmonwifiplus.

Responsibilities:
- set virtual outdoor temperature
- output hysteresis
- minimum write interval
- connection health
- bypass handling

### `mqtt`

Optional telemetry and command interface. MQTT failure must have no effect on the local controller.

### `web`

Local provisioning and status UI. This must remain an interface to configuration and diagnostics, not a second controller.

## Operating modes

Planned public modes:

- `safe`
- `normal`
- `holiday`
- `summer`
- `preheating`
- `pre_braking`
- `braking`
- `precooling`
- `cooling`

## Data ownership

PumpSteer Mini is the source of truth for:
- current operating mode
- calculated fake outdoor temperature
- selected BLE sensors
- local controller settings
- learned thermal model

Home Assistant may change supported settings through MQTT, but Mini stores and applies the final value locally.

## Failure behavior

### Internet unavailable

Continue using:
- indoor BLE
- outdoor BLE
- local PI control
- cached price/forecast while still fresh

Disable or degrade only the optimization that depends on stale external data.

### Price unavailable

Continue local PI control. Do not brake or preheat based on unknown price state.

### Forecast unavailable

Continue local PI and price braking. Do not trigger forecast-dependent preheat/precool.

### Indoor BLE stale

Indoor temperature is required by the PI loop. Request safe bypass rather than controlling from an old value.

### Outdoor BLE stale

Use an explicitly configured fallback only if it is fresh and valid. Otherwise request safe bypass.

### Ohmonwifiplus unavailable

Stop repeated aggressive writes, report output fault and request/rely on safe bypass behavior as supported by the installation.

## Learning architecture

Learning runs beside the controller:

```text
Sensors ─────> Controller ─────> Output
   │
   └─────────> Thermal learner ─────> model / predictions
                                      │
                                      └─ bounded advice only after validation
```

The rollout is deliberately staged:

1. collect only
2. predict in shadow mode
3. compare prediction vs reality
4. allow bounded assistance after sufficient confidence

## Storage

NVS stores compact durable state only:
- configuration
- sensor identities
- thermal model parameters
- model sample count/confidence
- schema version

High-frequency raw history should not be continuously written to flash.

## Reference hardware

Development target:
- ESP32-S3-WROOM-1-N16R8
- 16 MB flash
- 8 MB PSRAM

The firmware architecture must not require all 8 MB PSRAM so a future production board can be optimized if needed.
