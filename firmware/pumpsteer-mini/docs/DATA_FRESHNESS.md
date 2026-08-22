# Data freshness defaults

Initial intended freshness policy (subject to hardware testing):

- Indoor BLE: required and considered stale after a bounded timeout.
- Outdoor BLE: required unless an explicitly configured fresh fallback exists.
- Price data: usable only for the covered time slots; stale price data must not be extrapolated indefinitely.
- Forecast data: must carry retrieval/forecast timestamps and is never considered current forever.

Exact timeout values will be centralized in configuration/constants and tested before release.
