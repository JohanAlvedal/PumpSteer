# Release Notes

## Cheap-hours boost configuration update

- PumpSteer sensor now reads the cheap-hours boost strength and duration from the new helpers `input_number.pumpsteer_cheap_boost_delta` and `input_number.pumpsteer_cheap_boost_hours`, falling back to safe defaults when they are missing.
- The sensor attributes expose both the temperature delta and the focused cheap-hour window so dashboards and automations can show the planned boost.
- Documentation and Lovelace example cards have been refreshed to reflect the cheap boost vocabulary and the new helpers.
- Added a compatibility fallback so installations that still reference the previous utility module do not crash when updating only parts of the integration.

### Breaking changes

- The example package file now defines the two new input numbers listed above. Make sure to add them to your own `packages.yaml` (or create equivalent helpers) before updating, otherwise the cheap boost will revert to the default 0.5 °C over the three cheapest hours.
- The old "preboost" wording has been replaced by "cheap boost" in the UI helper names. Update any custom dashboards, automations or scripts that referenced the previous labels.

### Behaviour changes

- Cheap boost (formerly preboost) still targets the lowest-price hours of the day, but the temperature increase and number of target hours can now be tuned without editing YAML. Adjust the two helpers to pick how aggressively PumpSteer should heat during cheap periods.

