---
layout: default
title: Generic Output System
nav_order: 8
---

# PumpSteer Generic Output System (GOS)

## Overview

The PumpSteer Generic Output System (GOS) allows PumpSteer to send its calculated
virtual outdoor temperature (`fake_temp`) to virtually any Home Assistant compatible
target.

GOS transforms PumpSteer from a heat pump specific controller into a universal
temperature optimization engine.

The system is fully local and entirely based on Home Assistant service calls.

---

# Features

- Fully template-based payload generation
- Supports all Home Assistant services
- Supports MQTT, Modbus, REST, ESPHome and more
- Interval-based throttling
- Local only — no cloud dependencies
- Compatible with virtually any system reachable from Home Assistant
- Dynamic payload rendering using Jinja templates

---

# Supported Integrations

Examples of compatible systems:

- Thermia
- Nibe
- Mitsubishi
- Daikin
- ESPHome
- PLC systems
- MQTT brokers
- RS232 gateways
- REST APIs
- Node-RED
- Home Assistant helpers
- Custom integrations

---

# Configuration

## Generic Output Service

Defines which Home Assistant service should be called.

Example:

```text
modbus.write_register
````

Other examples:

```text id="ik6csn"
mqtt.publish
```

```text id="v6x1q7"
input_number.set_value
```

```text id="d9gx59"
rest_command.send_fake_temp
```

---

## Generic Output Payload Template

Defines the payload sent to the selected service.

The template has access to:

```jinja id="wwsc1d"
{{ fake_temp }}
```

which contains PumpSteer's current calculated virtual outdoor temperature.

The template must generate valid YAML/dictionary output.

---

## Generic Output Interval

Defines how often GOS sends updates.

Example:

```text id="f3x7wp"
1
```

= send every minute

---

# Example 1 — Home Assistant Helper

## Service

```text id="mcq5os"
input_number.set_value
```

## Payload

```yaml id="u9o2v9"
entity_id: input_number.outdoor_temp_bms
value: "{{ fake_temp | round(1) }}"
```

## Result

Updates a Home Assistant helper entity with the current fake temperature.

Useful for:

* testing
* dashboards
* debugging

---

# Example 2 — MQTT

## Service

```text id="21z5gj"
mqtt.publish
```

## Payload

```yaml id="8ysv9p"
topic: pumpsteer/fake_outdoor_temp
payload: "{{ fake_temp | round(1) }}"
retain: true
```

## Result

Publishes fake temperature to MQTT.

Useful for:

* Node-RED
* ESPHome
* external automation systems
* databases

---

# Example 3 — Modbus Register

## Service

```text id="5r7mgk"
modbus.write_register
```

## Payload

```yaml id="zq6ax2"
hub: thermia
slave: 1
address: 1000
value: "{{ (fake_temp * 100) | round(0) | int }}"
```

## Result

Writes the temperature value to a Modbus register.

Common for:

* Thermia
* Nibe
* PLC systems
* industrial controllers

---

# Example 4 — REST API

## Service

```text id="q1n31d"
rest_command.send_fake_temp
```

## Payload

```yaml id="g9m9o5"
temperature: "{{ fake_temp | round(1) }}"
```

## Result

Sends PumpSteer data to an external REST API.

---

# Example 5 — ESPHome Entity

## Service

```text id="gexu9f"
number.set_value
```

## Payload

```yaml id="v9h8z8"
entity_id: number.esphome_fake_outdoor_temp
value: "{{ fake_temp | round(1) }}"
```

## Result

Directly controls an ESPHome number entity.

---

# Example 6 — Logging

## Service

```text id="3x3c3z"
system_log.write
```

## Payload

```yaml id="hnd6m2"
message: "PumpSteer fake temp = {{ fake_temp | round(1) }}"
level: info
```

## Result

Writes values to the Home Assistant log for troubleshooting.

---

# Example 7 — JSON MQTT Payload

## Service

```text id="6pxm5z"
mqtt.publish
```

## Payload

```yaml id="g5f3y8"
topic: pumpsteer/status
payload: >
  {
    "fake_temp": {{ fake_temp | round(1) }},
    "timestamp": "{{ now() }}"
  }
retain: true
```

## Result

Publishes structured JSON data.

Useful for advanced integrations and external processing.

---

# Internal Architecture

GOS works by:

1. Reading the configured Home Assistant service
2. Rendering the configured Jinja payload template
3. Converting the rendered output into a valid dictionary
4. Calling the Home Assistant service asynchronously
5. Applying interval throttling to avoid excessive updates

---

# Safety

GOS includes:

* Payload validation
* YAML/dictionary validation
* Service name validation
* Exception handling
* Interval limiting
* Warning logging on failures

Invalid templates or invalid payloads will never crash PumpSteer.

---

# Design Philosophy

PumpSteer GOS is intentionally generic.

The goal is not to support one specific heat pump brand.

The goal is to allow PumpSteer to communicate with virtually any system
that Home Assistant can access.

This makes PumpSteer:

* hardware independent
* protocol independent
* future proof
* highly extensible

---

# Notes

* GOS is optional
* PumpSteer works normally without it
* All processing is local
* No cloud services are required
* Multiple external systems can be supported through Home Assistant

```
```
