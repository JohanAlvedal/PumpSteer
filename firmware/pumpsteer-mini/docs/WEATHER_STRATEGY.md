# Weather strategy notes

Weather data is used for anticipation, not as the preferred real outdoor measurement when a valid local BLE sensor is available.

Initial intended behavior:
- retain a 24-hour temperature forecast cache
- use up to six hours for control lookahead
- forecast-gate preheat
- forecast-gate precool
- disable forecast-dependent behavior when data is stale/missing
- keep local PI control independent of forecast availability
