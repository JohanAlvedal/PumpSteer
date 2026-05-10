---
layout: default
title: Generic Output System
nav_order: 7
---

# 🔌 Generic Output System (GOS)

## Overview

The PumpSteer Generic Output System (GOS) allows PumpSteer to send its calculated
virtual outdoor temperature (`fake_temp`) to a configurable Home Assistant service.

This makes it possible to connect PumpSteer to external systems such as helpers,
MQTT, Modbus, REST commands, ESPHome entities or other Home Assistant integrations.

GOS is experimental in PumpSteer 2.1.1 and should be tested carefully before being
used for production heating control.

---

## What has been tested

The following has been verified during development:

- `fake_temp` is passed to the output function
- the payload template is rendered correctly
- YAML payloads are parsed into service data
- `system_log.write` can be used for testing
- `input_number.set_value` can be used to write `fake_temp` to a helper

Other service targets, such as Modbus, MQTT or REST commands, depend on the user's
Home Assistant setup and should be verified individually.

---

## What GOS can be used for

GOS may be used with any Home Assistant service that accepts a YAML/dictionary payload.

Possible use cases include:

- writing to a Home Assistant helper
- publishing to MQTT
- writing to a Modbus register
- calling a REST command
- updating an ESPHome number entity
- triggering custom integrations or automations

PumpSteer does not include brand-specific protocol handling. The user is responsible
for configuring the correct Home Assistant service, register, topic, scaling and payload.

---

## Configuration

### Generic Output Service

The Home Assistant service to call.

Examples:

```text
input_number.set_value
````

```text
system_log.write
```

```text
mqtt.publish
```

```text
modbus.write_register
```

---

### Generic Output Payload Template

The YAML payload sent to the selected service.

The template has access to:

```jinja
{{ fake_temp }}
```

which contains PumpSteer's calculated virtual outdoor temperature.

The rendered template must produce a valid YAML dictionary.

---

## Example 1 — Home Assistant helper

### Service

```text
input_number.set_value
```

### Payload

```yaml
entity_id: input_number.outdoor_temp_bms
value: "{{ fake_temp | round(1) }}"
```

This writes the current PumpSteer fake temperature to an `input_number` helper.

---

## Example 2 — System log test

### Service

```text
system_log.write
```

### Payload

```yaml
message: "PumpSteer fake temp = {{ fake_temp | round(1) }}"
level: info
```

This writes the current value to the Home Assistant log and is useful for testing.

---

## Example 3 — MQTT

### Service

```text
mqtt.publish
```

### Payload

```yaml
topic: pumpsteer/fake_outdoor_temp
payload: "{{ fake_temp | round(1) }}"
retain: true
```

This publishes the fake temperature to MQTT.

This has not been tested in all setups and depends on a working MQTT integration.

---

## Example 4 — Modbus register

### Service

```text
modbus.write_register
```

### Payload

```yaml
hub: thermia
address: 118
value: "{{ (fake_temp * 100) | round(0) | int }}"
```

This example writes a scaled temperature value to a Modbus register.

The register address, hub name, scaling and optional slave/addressing parameters depend
on the specific heat pump, gateway, controller or Modbus setup.

---

## Example 5 — ESPHome number entity

### Service

```text
number.set_value
```

### Payload

```yaml
entity_id: number.esphome_fake_outdoor_temp
value: "{{ fake_temp | round(1) }}"
```

This can be used with an ESPHome number entity or similar Home Assistant number entity.

---

## Notes

* GOS is optional.
* PumpSteer works normally without it.
* The internal option keys currently still use the `modbus_*` prefix for backward compatibility.
* Output calls are interval-limited.
* Invalid templates or payloads are logged as warnings and should not stop PumpSteer.
* Always verify the output with `system_log.write` or an `input_number` helper before writing to real hardware.

```
