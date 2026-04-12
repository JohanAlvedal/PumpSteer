# Configuration

## Required entities

- Indoor temperature sensor  
- Outdoor temperature sensor  
- Electricity price sensor  

---

## Optional

- Weather entity  
- Tomorrow price sensor  

---

## How PumpSteer works

PumpSteer calculates a **virtual outdoor temperature** based on:

- Indoor temperature  
- Target temperature  
- Electricity price  
- Weather forecast  
- Aggressiveness level  

---

## Ohmigo integration

PumpSteer can push values directly to an Ohmigo device.

### Behavior

- Rounded to 0.5°C  
- Hysteresis (~0.2°C)  
- Rate limited updates  

---

## Switches

- `switch.pumpsteer_preheat_boost`
- `switch.pumpsteer_ohmigo_enabled`
