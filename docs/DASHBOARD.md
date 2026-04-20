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

{: .important }
The YAML examples below are based on a real PumpSteer installation and may need to be
adapted to match your setup. In particular, replace any entity IDs that are specific
to this installation (such as `sensor.elpris_spot_avgifter` and `sensor.temperatur_nu`)
with your own entity IDs. All PumpSteer-owned entities (prefixed `sensor.pumpsteer`,
`number.pumpsteer`, `switch.pumpsteer`, `datetime.pumpsteer`) are registered
automatically and do not need to be changed.

---

## Prerequisites

Install these cards via HACS before using the dashboard templates:

- [**mini-graph-card**](https://github.com/kalkih/mini-graph-card) — for temperature and price charts
- [**apexcharts-card**](https://github.com/RomRider/apexcharts-card) *(optional)* — for advanced charts

---

## PumpSteer entities reference

### Sensors

| Entity | State | Key attributes |
|---|---|---|
| `sensor.pumpsteer` | Fake outdoor temperature (°C) | `mode`, `price_category`, `brake_factor`, `heating_demand_c`, `p30`, `p80`, `indoor_temperature`, `outdoor_temperature`, `minutes_until_expensive`, `status`, `last_updated` |
| `sensor.pumpsteer_thermal_outlook` | `preheat` / `neutral` / `warming` / `precool_risk` | `preheat_worthwhile`, `preheat_strength`, `warming_trend`, `cooling_trend`, `night_min_temp`, `day_max_temp` |

### Numbers

| Entity | Description |
|---|---|
| `number.pumpsteer_target_temperature` | Target indoor temperature |
| `number.pumpsteer_summer_mode_threshold` | Summer mode activation temperature |
| `number.pumpsteer_saving_level` | Aggressiveness / saving level (0–5) |
| `number.pumpsteer_house_thermal_mass` | Brake ramp time (house inertia) |

### Switches

| Entity | Description |
|---|---|
| `switch.pumpsteer_preheat_boost` | Preheat boost on/off |
| `switch.pumpsteer_notifications` | Price notifications on/off |
| `switch.pumpsteer_holiday_mode` | Holiday mode on/off |
| `switch.pumpsteer_ohmigo_push` | Ohmigo push on/off |

### Datetime helpers

| Entity | Description |
|---|---|
| `datetime.pumpsteer_holiday_start` | Holiday start (auto-activates holiday mode) |
| `datetime.pumpsteer_holiday_end` | Holiday end (auto-deactivates holiday mode) |

---

## Control panel

Settings and switches for quick adjustment directly from the dashboard.

{: .note }
This example uses `sensor.elpris_spot_avgifter` as the electricity price entity.
Replace this with your own price sensor entity ID.

```yaml
type: grid
columns: 1
cards:
  - type: vertical-stack
    cards:
      - type: glance
        show_name: true
        show_icon: true
        show_state: true
        columns: 3
        entities:
          - entity: sensor.pumpsteer_operating_mode
            name: Mode
          - entity: sensor.pumpsteer_price
            name: Price
          - entity: sensor.pumpsteer_brake_factor
            name: Brake
  - type: vertical-stack
    cards:
      - type: entities
        title: Settings
        show_header_toggle: false
        entities:
          - entity: number.pumpsteer_target_temperature
            name: Target Temperature
            icon: mdi:thermometer
          - entity: number.pumpsteer_saving_level
            name: Aggressiveness (0 = Off, 5 = Max)
            icon: mdi:lightning-bolt-circle
          - entity: number.pumpsteer_summer_mode_threshold
            name: Summer Threshold
            icon: mdi:weather-sunny
          - entity: number.pumpsteer_house_thermal_mass
            icon: mdi:home-thermometer
          - entity: switch.pumpsteer_notifications
            name: Notifications
          - entity: switch.pumpsteer_ohmigo_push
            name: Ohmigo Push
          - entity: switch.pumpsteer_preheat_boost
          - entity: datetime.pumpsteer_holiday_start
            name: Holiday Start
          - entity: datetime.pumpsteer_holiday_end
            name: Holiday End
          - entity: switch.pumpsteer_holiday_mode
            name: Holiday Mode
          - entity: sensor.pumpsteer_thermal_outlook
  - type: custom:mini-graph-card
    name: Price vs P30 / P80 (12h)
    hours_to_show: 12
    points_per_hour: 4
    line_width: 3
    font_size: 75
    animate: true
    show:
      labels: false
      legend: true
      icon: false
    entities:
      - entity: sensor.elpris_spot_avgifter  # ← replace with your price entity
        name: Price
        show_state: true
      - entity: sensor.pumpsteer
        attribute: p30
        name: P30
        show_state: true
      - entity: sensor.pumpsteer
        attribute: p80
        name: P80
        show_state: true
```

---

## Data overview

Detailed status card showing all sensor attributes.

{: .note }
Replace `sensor.elpris_spot_avgifter` with your electricity price entity ID.

```yaml
type: grid
cards:
  - type: entities
    title: PumpSteer Data
    entities:
      - type: attribute
        entity: sensor.pumpsteer
        attribute: status
        name: Status
        icon: mdi:check-circle
      - type: attribute
        entity: sensor.pumpsteer
        attribute: mode
        name: Mode
        icon: mdi:cog
      - type: attribute
        entity: sensor.pumpsteer
        attribute: price_category
        name: Price Category
        icon: mdi:tag
      - entity: sensor.pumpsteer
        icon: mdi:thermometer-chevron-down
        name: Virtual Outdoor Temperature
        secondary_info: last-changed
      - type: attribute
        entity: sensor.pumpsteer
        attribute: indoor_temperature
        name: Indoor Temperature
        suffix: °C
        icon: mdi:home-thermometer
      - type: attribute
        entity: sensor.pumpsteer
        attribute: outdoor_temperature
        name: Outdoor Temperature
        suffix: °C
        icon: mdi:thermometer
      - type: attribute
        entity: sensor.pumpsteer
        attribute: p30
        name: Price P30 Today
        suffix: SEK/kWh
        icon: mdi:chart-bell-curve
      - type: attribute
        entity: sensor.pumpsteer
        attribute: p80
        name: Price P80 Today
        suffix: SEK/kWh
        icon: mdi:chart-bell-curve
      - entity: sensor.elpris_spot_avgifter  # ← replace with your price entity
        name: Price Now
        secondary_info: last-changed
      - type: attribute
        entity: sensor.pumpsteer
        attribute: last_updated
        name: Last Updated
        icon: mdi:clock-outline
      - type: attribute
        entity: sensor.pumpsteer
        attribute: minutes_until_expensive
        name: Minutes to Expensive
        icon: mdi:chart-bell-curve
        suffix: min
  - type: custom:mini-graph-card
    name: Real vs PumpSteer Temperatures
    icon: mdi:thermometer-lines
    entities:
      - entity: sensor.pumpsteer
        name: PumpSteer Temp
        color: "#e87d0d"
        show_state: true
      - entity: sensor.temperatur_nu  # ← replace with your outdoor temp entity
        name: Outdoor Temp
        color: "#44739e"
        show_state: true
    hours_to_show: 24
    points_per_hour: 4
    line_width: 2
    smoothing: true
    show:
      labels: true
      points: false
      legend: true
      fill: fade
```

---

## Mode color indicator

A template sensor for color-coding the current mode — useful in custom cards.
Add this to `configuration.yaml` or a package file:

{% raw %}
```yaml
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
{% endraw %}

---

## Automation examples

### Notify when braking starts

{: .note }
Replace `notify.mobile_app_my_phone` with your own notification service.

{% raw %}
```yaml
alias: PumpSteer — braking started
trigger:
  - platform: state
    entity_id: sensor.pumpsteer
    attribute: mode
    to: braking
action:
  - service: notify.mobile_app_my_phone  # ← replace with your notify service
    data:
      title: "⚡ Price braking active"
      message: >
        Electricity is expensive. Heating reduced.
        Indoor: {{ state_attr('sensor.pumpsteer', 'indoor_temperature') }} °C
```
{% endraw %}

### Lower target when away

{: .note }
Replace `person.you` with your own person entity.

```yaml
alias: PumpSteer — away mode
trigger:
  - platform: state
    entity_id: person.you  # ← replace with your person entity
    to: not_home
action:
  - service: number.set_value
    target:
      entity_id: number.pumpsteer_target_temperature
    data:
      value: 18
```
