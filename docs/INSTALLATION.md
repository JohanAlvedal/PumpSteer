# Installation

## New installation

1. Install via HACS or manually  
2. Restart Home Assistant  
3. Add PumpSteer integration  
4. Select required sensors  

---

## First validation

Check:

- sensor.pumpsteer exists  
- status = ok  
- price_category updates  
- mode changes over time  

---

## Upgrade from 1.6.6

### Required

- Update price categories  
- Configure tomorrow price  
- Update automations  
- Remove ML  

### Recommended

- Verify price attributes  
- Configure weather entity  
