# PumpSteer V3 Comfort Beta rollout

Status: working checklist for `3.0.0-beta.1`. This is not a stable-release claim.

## Beta promise

The first V3 beta proves safe comfort control and safe physical delivery. It includes
shadow mode, OhmOnWiFi MQTT, and the V3 Generic Output System (GOS). Price analysis,
weather data, saving level, and observation-only learning do not have physical-control
authority in this beta.

## Implemented foundation

- Bidirectional bounded comfort control with anti-windup.
- Comfort floor and ceiling.
- Summer passthrough with hysteresis.
- Plausible indoor and outdoor temperature ranges.
- Multi-observation recovery guard after fail-safe.
- Safe startup baseline so the first active output is step and slew limited.
- Explicit virtual-outdoor-temperature heat curve in closed-loop simulation.
- Shadow, OhmOnWiFi MQTT, and GOS output modes.
- GOS safe action on initialize, shutdown, controller fallback, write failure, and
  software-watchdog timeout.
- Non-destructive handling of V2 entries: automatic V2-to-V3 migration is refused.
- Full tests are required in the release workflow.

## P0 gates before active beta

- Add source-aware frozen-sensor and rate-of-change detection for both critical
  sensors, including fault-injection tests.
- Add an independent frost-protection policy.
- Persist or deliberately reset summer/recovery/controller state across Home
  Assistant restart, with deterministic restart tests.
- Add a bounded transition policy for large target-temperature changes.
- Feed final supervisor saturation back into controller anti-windup or prove the
  current bounds cannot accumulate harmful integral state.
- Add simulator scenarios for light radiator, heavy radiator, underfloor heating,
  mixed systems, open windows, solar/internal gains, compressor saturation, and
  hot-water interruption.
- Verify OhmOnWiFi device watchdog and feedback behavior on real spare hardware.
- Commission GOS safe behavior with harmless services before any heating hardware.
- Write and rehearse the rollback procedure on a separate test installation.

## Rollout sequence

1. Run at least 48–72 hours in shadow mode for each representative heating-system
   profile.
2. Review comfort error, output movement, fail-safe transitions, and recovery events.
3. Enable active output only on the spare OhmOnWiFi installation and deliberately test
   stale sensors, service/broker failure, reload, and Home Assistant restart.
4. Admit a very small closed beta only after all P0 gates pass.
5. Publish `3.0.0-beta.1`; do not publish V3 as stable until the complete safety
   contract and field evidence are satisfied.

## V2 coexistence and rollback

Do not install this beta over the only working V2 production installation. Keep the V2
config entry and its options untouched. Only one controller may have physical write
authority to a heat pump.

Rollback order:

1. Select shadow output or disable the V3 entry.
2. Verify physical bypass at the output device.
3. Stop/remove the V3 test installation.
4. Restore V2 on the production installation.
5. Verify V2 sensors, entity IDs, physical output, and one Home Assistant restart.

## Explicitly excluded from beta 1

- Physical price-driven preheating or curtailment.
- Physical weather-driven planning.
- Any physical authority from learning.
- Self-modifying PI gains.
- GOS without a tested safe action.
- Broad automatic V2 upgrade through HACS.
- Claims of measured energy or cost savings.
