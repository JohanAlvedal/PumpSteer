# 🚀 Installation & Upgrade Guide

## New Installation
1. Install via HACS (Custom Repository) or manually.
2. Restart Home Assistant.
3. Add the integration: **Settings** → **Devices & Services** → **Add Integration** → **PumpSteer**.
4. Select your required sensors (indoor temp, price, weather).

### First validation
- Ensure `sensor.pumpsteer` is active.
- Status should be `ok`.
- Check that `price_category` changes and `mode` behaves logically.

---

## Upgrade from 1.6.6 ⚠️
PumpSteer 2.0.0 is a **complete rewrite**. Treat this as a new integration.

### Required actions:
* **Price Categories:** Update your sensors. Old categories like `very_cheap` or `extreme` are gone. New ones are `cheap`, `normal`, and `expensive`.
* **Forecast:** Configure tomorrow's price sensor.
* **Automations:** Update any automations pointing to old entities.
* **ML:** Machine Learning features have been removed.

### Recommendations:
1. Install 2.0.0.
2. Observe for 24–48h.
3. Then migrate fully and rebuild Lovelace cards.
