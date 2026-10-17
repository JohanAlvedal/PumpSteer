# Ohmigo ACTIVE renewal after validated temperature output

This change depends on the temperature-input qualification and dispatch checks
in [PR #279](https://github.com/JohanAlvedal/PumpSteer/pull/279), commit
`dc87d8f5b432fcf71cd5653febad37265af38553`. It changes only `ohmigo.py` and
`relay_guard.py` at runtime. PI regulation, comfort protection and temperature
source selection are unchanged.

## Problem and fix

Previously, Relay Guard could reactivate an OFF relay without a new successful
temperature write, including when invalid temperature inputs had stopped output.
Conversely, an already ON relay did not receive regular ACTIVE renewal.

The number service call is now awaited. A successful, still-valid temperature
write grants one runtime-only opportunity for Guard to send ACTIVE. Guard
rechecks the existing temperature qualification before each attempt. A temporary
source listener latches changes during the number/Guard sequence, including a
source that becomes invalid and then returns to the same value. The listener
is removed when the sequence finishes. Periodic checks, relay state changes and
restored states cannot independently renew this permission.

The existing recovery task and bounded three-attempt path also renew an already
ON relay after a validated write. Guard/Push OFF, unload, unavailable relay,
invalid sources and failed temperature service calls prevent ACTIVE renewal.
Safe mode may intentionally forward valid outdoor temperature when indoor data
or prices are missing; it does not reuse a previous calculated temperature.

## Hardware contract and limits

For Ohmonwifi Plus firmware 1.1.9, the manufacturer confirmed automatic BYPASS
on communication loss or power loss and a 900-second MQTT watchdog requiring
regular ACTIVE commands. The manufacturer also reports this safety feature for
G2. **Automatic BYPASS is implemented by the hardware, not by this change.**
The tests model that contract; they are not firmware or physical-device tests.

Use the existing **five-minute output interval** for margin below 900 seconds.
Guard rejects invalid intervals and intervals of at least 15 minutes without
changing user settings. Intervals just below 15 minutes still leave insufficient
margin for delays. No new watchdog, polling loop, integration, entity or
persistent state is introduced. Normal simulation sends seven temperature and
seven ACTIVE commands over 30 minutes, including the initial pair.

Awaiting the HA number service establishes service-dispatch ordering, not a
device-applied acknowledgement. MQTT delivery and physical temperature
application are not proved by a successful service call. The effect of a
temperature command on the hardware watchdog is unspecified; tests cover both
possibilities. HA report metadata is not proof of physical measurement age.
Already dispatched commands cannot be recalled. After input failure, the last
output may remain until the hardware watchdog enters BYPASS; immediate BYPASS
is not promised.

## Verification

Run the offline suite from the repository root:

```bash
python3 -m pytest -q
ruff check
ruff format --check
python3 scripts/check_version.py
git diff --check
```

Use Ruff **0.15.8**, matching the existing CI workflow. The full lint and format
checks pass with that version; the critical runtime lint subset also passes.

The combined offline suite passes 344 cases, including startup/restore markers,
input loss/recovery, failed services, source flapping during awaits, unload,
bounded retries, ordinary keepalive, clock rollback and a simulated receiver
with a 900-second watchdog. Offline tests use HA stubs.

An optional real-Core service/event-loop probe can be run with an isolated
Home Assistant Core 2026.10.1 Python environment and a new empty configuration
path outside production:

```bash
PYTHONDONTWRITEBYTECODE=1 /path/to/isolated-ha/bin/python -B tests/probes/ohmigo_active_core.py /path/to/new-test-config
```

Its five scenarios cover startup without sources, awaited number-before-ACTIVE,
input loss/recovery before the next allowed output, failed number service and
subsequent successful output. Sources/services are synthetic and Guard waits
are accelerated. This is not a full installation, disk-restore or physical
MQTT/relay test. Internal separate code review found no significant remaining
issue; it does not replace physical verification.

## Controlled installation and rollback

Install a coherent release containing both PR #279 and this fix. Preserve
temperature bindings and the five-minute interval. Back up integration files
and options with verified restore before updating. Disable Guard/Push and
verify hardware BYPASS using the installation's approved procedure. Check
configuration and load the updated code through a supported, approved method.
With Guard OFF, verify current temperature output first; only then enable Guard
under observation for at least two normal intervals. Distinguish broker
forwarding, device reports and physical application.

On failure, disable Guard/Push, verify BYPASS and restore the coherent backup
using the approved code-loading method. Do not re-enable the old Guard's known
unqualified recovery while temperature input is invalid. No production action
is performed by this PR.
