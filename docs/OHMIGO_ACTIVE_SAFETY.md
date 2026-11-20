---
layout: default
title: Ohmigo ACTIVE renewal
nav_order: 8
---

# 🛡️ Ohmigo ACTIVE renewal
{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

This page describes how PumpSteer keeps an Ohmigo receiver in ACTIVE mode, and why
ACTIVE is only renewed after a validated temperature write. It applies to installations
that use **Ohmigo Push** together with the optional **Ohmigo Relay Guard**
(`switch.pumpsteer_ohmigo_relay_guard`). PI regulation, comfort protection and
temperature source selection are not affected.

---

## How it works

ACTIVE is tied to output, not to time:

- The Ohmigo number service call is awaited. Only a **successful, still-valid
  temperature write** grants Relay Guard one runtime-only opportunity to send ACTIVE.
- Relay Guard rechecks the temperature-input qualification before each attempt.
- A temporary source listener latches changes during the number/Guard sequence,
  including a source that becomes invalid and then returns to the same value. The
  listener is removed when the sequence finishes.
- Periodic checks, relay state changes and restored states cannot renew this
  permission on their own.
- The bounded three-attempt recovery path also renews an **already ON** relay after a
  validated write, so the receiver's watchdog keeps receiving ACTIVE.

ACTIVE is **not** renewed when Guard or Push is off, the integration is unloading, the
relay is unavailable, source temperatures are invalid, or the temperature service call
failed.

Safe mode may intentionally forward a valid real outdoor temperature when indoor data
or prices are missing. It never reuses a previously calculated temperature.

---

## Hardware contract and limits

For Ohmonwifi Plus firmware 1.1.9, the manufacturer confirmed automatic BYPASS on
communication loss or power loss, and a 900-second MQTT watchdog that requires regular
ACTIVE commands. The manufacturer reports the same safety feature for G2.

{: .important }
Automatic BYPASS is implemented by the **hardware**, not by PumpSteer. The tests model
that contract; they are not firmware or physical-device tests.

- Use the default **five-minute output interval** for margin below 900 seconds. Guard
  rejects invalid intervals and intervals of 15 minutes or more without changing your
  settings. Intervals just below 15 minutes still leave too little margin for delays.
- No extra watchdog, polling loop, entity or persistent state is added. In normal
  operation PumpSteer sends seven temperature and seven ACTIVE commands per 30 minutes,
  including the initial pair.
- Awaiting the HA number service guarantees dispatch order, not that the device applied
  the value. MQTT delivery and physical application are not proved by a successful
  service call. HA report metadata is not proof of physical measurement age.
- Already dispatched commands cannot be recalled. After an input failure the last
  output may remain until the hardware watchdog enters BYPASS; immediate BYPASS is not
  promised.

---

## Commissioning

When you first enable Relay Guard on an installation:

1. Turn Guard and Push off and verify that the receiver enters BYPASS using your
   installation's procedure.
2. With Guard still off, turn Push on and verify that temperature output arrives.
3. Turn Guard on and observe at least two normal output intervals. Distinguish broker
   forwarding, device reports and physical application.

If something is wrong, turn Guard and Push off and verify BYPASS before troubleshooting.

---

## Testing

The offline test suite covers startup/restore, input loss and recovery, failed
services, source flapping during awaits, unload, bounded retries, ordinary keepalive,
clock rollback and a simulated receiver with a 900-second watchdog. Run it from the
repository root:

```bash
python3 -m pytest -q
```

An optional probe against a real Home Assistant Core event loop can be run in an
isolated Core environment with a new, empty configuration directory (never a
production configuration):

```bash
PYTHONDONTWRITEBYTECODE=1 /path/to/isolated-ha/bin/python -B tests/probes/ohmigo_active_core.py /path/to/new-test-config
```

Sources and services in the probe are synthetic and Guard waits are accelerated. It is
not a physical MQTT/relay test.
