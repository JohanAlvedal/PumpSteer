---
layout: default
title: Dashboard Setup
nav_order: 4
---

# 📊 Dashboard Setup
{: .no_toc }

<details open markdown="block">
  <summary>Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Prerequisites

Install these cards via HACS before using the dashboard templates:

- [**mini-graph-card**](https://github.com/kalkih/mini-graph-card) — for temperature history charts
- [**apexcharts-card**](https://github.com/RomRider/apexcharts-card) — for price and mode visualization
- [**Mushroom Cards**](https://github.com/piitaya/lovelace-mushroom) *(optional)* — for compact entity chips

---

## PumpSteer entities reference

These are the entity IDs PumpSteer registers. Use them in your own cards.

### Sensors

| Entity | State | Key attributes |
|---|---|---|
| `sensor.pumpsteer` | Fake outdoor temperature (°C) | `mode`, `price_category`, `brake_factor`, `heating_demand_c`, `p30`, `p80`, `indoor_temperature`, `target_temperature`, `outdoor_temperature` |
| `sensor.pumpsteer_thermal_outlook` | `preheat` / `neutral` / `warming` / `precool_risk` | `preheat_worthwhile`, `preheat_strength`, `warming_trend`, `cooling_trend`, `night_min_temp`, `day_max_temp`, `hours_below_threshold` |

### Numbers

| Entity | Description |
|---|---|
| `number.pumpsteer_target_temperature` | Target indoor temperature |
| `number.pumpsteer_summer_mode_threshold` | Summer mode activation temperature |
| `number.pumpsteer_saving_level` | Aggressiveness / saving level |
| `number.pumpsteer_brake_ramp_time` | Brake ramp time (house inertia) |

### Switches

| Entity | Description |
|---|---|
| `switch.pumpsteer_preheat_boost` | Preheat boost on/off |
| `switch.pumpsteer_notifications` | Price notifications on/off |
| `switch.pumpsteer_holiday_mode` | Holiday mode on/off |
| `switch.pumpsteer_ohmigo_enabled` | Ohmigo push on/off |

---

## Minimal status card

A simple card showing current state at a glance:

```yaml
type: entities
title: PumpSteer
entities:
  - entity: sensor.pumpsteer
    name: Fake outdoor temp
  - type: attribute
    entity: sensor.pumpsteer
    attribute: mode
    name: Mode
  - type: attribute
    entity: sensor.pumpsteer
    attribute: price_category
    name: Price category
  - type: attribute
    entity: sensor.pumpsteer
    attribute: brake_factor
    name: Brake factor
  - type: attribute
    entity: sensor.pumpsteer
    attribute: indoor_temperature
    name: Indoor temp
  - entity: number.pumpsteer_target_temperature
    name: Target temp
  - entity: number.pumpsteer_saving_level
    name: Saving level
```

---

## Temperature history chart

Requires `mini-graph-card`:

```yaml
type: custom:mini-graph-card
name: PumpSteer temperatures
entities:
  - entity: sensor.pumpsteer
    name: Fake outdoor
    color: '#e74c3c'
  - entity: sensor.YOUR_INDOOR_SENSOR
    name: Indoor
    color: '#2ecc71'
  - entity: sensor.YOUR_OUTDOOR_SENSOR
    name: Real outdoor
    color: '#3498db'
hours_to_show: 24
points_per_hour: 4
line_width: 2
show:
  legend: true
  labels: true
```

Replace `sensor.YOUR_INDOOR_SENSOR` and `sensor.YOUR_OUTDOOR_SENSOR` with your
actual entity IDs.

---

## Mode color indicator

A template sensor you can use to color-code the current mode:

```yaml
# Add to configuration.yaml or a package file
template:
  - sensor:
      - name: PumpSteer Mode Color
        state: >
          {% set mode = state_attr('sensor.pumpsteer', 'mode') %}
          {% if mode == 'braking' %} red
          {% elif mode == 'pre_braking' %} orange
          {% elif mode == 'preheating' %} blue
          {% elif mode == 'summer_mode' %} yellow
          {% elif mode == 'safe_mode' %} grey
          {% else %} green
          {% endif %}
```

---

## Brake factor gauge

Requires `apexcharts-card`:

```yaml
type: custom:apexcharts-card
header:
  title: Brake factor
  show: true
chart_type: radialBar
series:
  - entity: sensor.pumpsteer
    attribute: brake_factor
    name: Brake
    min: 0
    max: 1
    color: '#e74c3c'
apex_config:
  plotOptions:
    radialBar:
      dataLabels:
        value:
          formatter: |
            EVAL:function(val) { return (val * 1).toFixed(2) }
```

---

## Price overview with mode overlay

Requires `apexcharts-card`. Shows electricity prices for today with the current
price category color:

```yaml
type: custom:apexcharts-card
header:
  title: Electricity price today
  show: true
graph_span: 24h
span:
  start: day
series:
  - entity: sensor.pumpsteer
    attribute: p80
    name: P80 threshold
    type: line
    color: '#e74c3c'
    stroke_width: 1
    curve: stepline
  - entity: sensor.pumpsteer
    attribute: p30
    name: P30 threshold
    type: line
    color: '#2ecc71'
    stroke_width: 1
    curve: stepline
```

---

## Thermal Outlook card

Shows the current forecast analysis from `sensor.pumpsteer_thermal_outlook`:

```yaml
type: entities
title: Thermal Outlook
entities:
  - entity: sensor.pumpsteer_thermal_outlook
    name: Outlook state
  - type: attribute
    entity: sensor.pumpsteer_thermal_outlook
    attribute: preheat_worthwhile
    name: Preheat worthwhile
  - type: attribute
    entity: sensor.pumpsteer_thermal_outlook
    attribute: preheat_strength
    name: Preheat strength
  - type: attribute
    entity: sensor.pumpsteer_thermal_outlook
    attribute: night_min_temp
    name: Night min temp
  - type: attribute
    entity: sensor.pumpsteer_thermal_outlook
    attribute: day_max_temp
    name: Day max temp
  - type: attribute
    entity: sensor.pumpsteer_thermal_outlook
    attribute: warming_trend
    name: Warming trend
  - type: attribute
    entity: sensor.pumpsteer_thermal_outlook
    attribute: cooling_trend
    name: Cooling trend
```

---

## Control panel

Sliders and switches for quick adjustment:

```yaml
type: entities
title: PumpSteer controls
entities:
  - entity: number.pumpsteer_target_temperature
  - entity: number.pumpsteer_saving_level
  - entity: number.pumpsteer_brake_ramp_time
  - entity: number.pumpsteer_summer_mode_threshold
  - type: divider
  - entity: switch.pumpsteer_preheat_boost
  - entity: switch.pumpsteer_holiday_mode
  - entity: switch.pumpsteer_notifications
  - entity: switch.pumpsteer_ohmigo_enabled
```

---

## Automation examples

### Notify when braking starts

```yaml
alias: PumpSteer — braking started
trigger:
  - platform: state
    entity_id: sensor.pumpsteer
    attribute: mode
    to: braking
action:
  - service: notify.mobile_app_my_phone
    data:
      title: "⚡ Price braking active"
      message: >
        Electricity is expensive. Heating reduced.
        Indoor: {{ state_attr('sensor.pumpsteer', 'indoor_temperature') }} °C
```

### Lower target when away

```yaml
alias: PumpSteer — away mode
trigger:
  - platform: state
    entity_id: person.you
    to: not_home
action:
  - service: number.set_value
    target:
      entity_id: number.pumpsteer_target_temperature
    data:
      value: 18
```
