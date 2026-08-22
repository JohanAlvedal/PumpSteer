# Precool safety notes

Precooling is intentionally not activated until active-cooling behavior has been verified for the connected heat-pump/Ohmonwifiplus setup.

Requirements before activation:
- cooling capability is explicitly configured
- fake-temperature direction/semantics are verified
- cooling comfort ceiling is separate from heating comfort floor
- price/weather lookahead is bounded
- precool cannot run from missing/stale forecast data
- safe mode and bypass behavior are tested in cooling season
