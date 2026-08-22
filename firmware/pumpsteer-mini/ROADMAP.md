# PumpSteer Mini Roadmap

PumpSteer Mini is a standalone ESP32-S3 controller for local heat-pump optimization. Home Assistant is optional; the controller must remain fully functional without it.

## Product goals

- Fully local control after initial internet data has been fetched.
- Indoor and outdoor temperature from BLE sensors, with Shelly BLU H&T as a first-class supported device.
- Direct local control of Ohmonwifiplus.
- Electricity-price-aware heating optimization.
- Weather-aware preheating and precooling.
- Aggressiveness levels 0-5.
- Safe degradation when internet, BLE, MQTT, or Home Assistant is unavailable.
- Optional MQTT and Home Assistant Discovery for monitoring and control.
- Explainable, bounded passive learning of the building thermal response.

## Phase 0 - Foundation ✅

- ESP-IDF project skeleton.
- ESP32-S3 reference target.
- Hardware-independent PumpSteer Core.
- PI controller with anti-windup.
- PI integral freeze during braking.
- Safe mode and bypass request.
- Summer passthrough.
- Aggressiveness 0-5.
- Comfort floor.
- Brake ramp with 60-second dt cap.
- Pre-brake and preheat hooks.
- Precooling represented in the public API.
- Host-side unit tests.

## Phase 1 - BLE temperature sensors 🚧

- BTHome v2 decoder. ✅
- Shelly BLU H&T temperature, humidity, battery, packet ID. ✅
- Passive ESP-NimBLE scanner. ✅
- Sensor registry and freshness tracking. ✅
- Indoor/outdoor role assignment. ✅
- Persist selected BLE sensors in NVS.
- Support encrypted BTHome devices with user-provided bind key.
- Add additional BTHome-compatible sensors where practical.

## Phase 2 - Device provisioning

- Wi-Fi provisioning access point.
- Local web setup page.
- NVS configuration store.
- mDNS hostname: pumpsteer.local.
- Configure location/coordinates.
- Configure electricity area SE1-SE4.
- Select indoor and outdoor BLE sensors.
- Configure/discover Ohmonwifiplus.
- Factory reset path.

## Phase 3 - Ohmonwifiplus output

- Local HTTP client.
- Device discovery where reliable.
- Temperature push with rounding and hysteresis.
- Configurable minimum push interval.
- Health/status polling.
- Explicit bypass support.
- Fail-safe behavior when Ohmonwifiplus cannot be reached.

## Phase 4 - Electricity prices

- Provider interface independent of the control core.
- First Swedish price provider for SE1-SE4.
- 15-minute price slots.
- Today/tomorrow cache.
- P30/P80 classification.
- Absolute cheap-price limit.
- Daily-stable thresholds.
- Six-hour price lookahead.
- Local cached operation during temporary internet loss.

## Phase 5 - Weather forecast

- Provider interface independent of the control core.
- First provider: Open-Meteo or equivalent no-key provider.
- Current conditions as fallback only; local outdoor BLE remains preferred.
- 24-hour temperature forecast cache.
- Six-hour control lookahead.
- Forecast freshness and stale-data handling.

## Phase 6 - Heating strategy parity

- Full expensive-price braking.
- Pre-brake before expensive blocks.
- Forecast-gated preheat.
- Bounded preheat strength.
- Brake hold across short price dips.
- Holiday mode.
- Verify output parity against selected PumpSteer Home Assistant test vectors.

## Phase 7 - Precooling

- Explicit cooling capability configuration.
- Separate cooling comfort ceiling.
- Weather + price lookahead.
- Pre-cool only when active cooling semantics are verified for the connected heat pump/Ohmonwifiplus installation.
- Bounded pre-cool target and duration.
- Never infer that cooling is available from summer weather alone.

## Phase 8 - Passive thermal learning

The learning system learns the building, not the control rules.

Stage A - passive observation:
- Estimate heat-loss coefficient from valid observation windows.
- Track sample count and confidence.
- Persist compact model to NVS.
- Expose learned values for diagnostics.
- Do not affect control output.

Stage B - shadow predictions:
- Predict expected indoor-temperature drop during a planned brake.
- Predict approximate response delay.
- Compare predictions with actual outcomes.
- Still do not affect control output.

Stage C - bounded assistance:
- Allow learned model to adjust preheat/precool timing within hard limits.
- Allow learned model to reduce an unsafe planned brake.
- Never modify PI gains, user target, aggressiveness, or comfort limits automatically.
- Provide a user-visible reset of the learned model.

## Phase 9 - MQTT / Home Assistant

- Optional MQTT client.
- Home Assistant MQTT Discovery.
- Temperature, price, forecast, mode, brake, preheat, precool and system-health sensors.
- Target-temperature and aggressiveness controls.
- Holiday mode.
- Force bypass.
- Learning confidence and model diagnostics.
- MQTT/Home Assistant must never be required for control.

## Phase 10 - Production readiness

- OTA firmware updates.
- Rollback-safe update strategy.
- Task watchdogs.
- Brownout/reboot recovery.
- Configuration schema versioning and migration.
- Long-run soak tests.
- Wi-Fi/BLE coexistence tests.
- Sensor-loss and internet-loss fault injection.
- Ohmonwifiplus communication fault injection.
- Release artifacts and installation documentation.

## Permanent design constraints

1. PI remains the primary feedback loop.
2. Price and forecast are bounded overlays.
3. Each signal influences control once only.
4. Comfort limits always override savings.
5. The PI integral is frozen during braking.
6. Pre-brake is a price signal; preheat is forecast-gated.
7. Local outdoor BLE is preferred over internet current temperature.
8. Missing internet must not stop local comfort control.
9. Missing required local temperature data must lead to a safe state/bypass request.
10. Learning must remain explainable, passive-first, confidence-gated and bounded.
11. Home Assistant and MQTT are optional interfaces, never dependencies.
12. No cloud account is required for local heat-pump control.
