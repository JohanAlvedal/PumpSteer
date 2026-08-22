# Release checklist

Use this checklist before a tagged PumpSteer Mini release.

- Host tests pass.
- ESP32-S3 firmware builds from a clean checkout.
- No credentials or local secrets are present.
- Safe mode and stale-sensor handling are verified.
- Ohmonwifiplus output bounds are verified.
- Price/weather failures degrade safely.
- BLE indoor/outdoor freshness is verified.
- OTA rollback is verified once OTA is implemented.
- `CHANGELOG.md` is updated.
- `VERSION` is updated.
- `ROADMAP.md` reflects delivered scope.
