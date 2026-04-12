# 🛠 Troubleshooting

### Safe Mode
**Cause:** Usually missing or invalid price data.
**Fix:** Check that your price sensor provides `today/raw_today` and `tomorrow/raw_tomorrow`.

### No Braking Occurring
**Cause:** - Price is not in the "Expensive" range.
- Comfort protection is active (indoor temp is too low).

### Wrong Price Category
**Cause:** Invalid data format from your price sensor. PumpSteer supports:
- `0.95`
- `{ "value": 0.95 }`
- `{ "price": 0.95 }`

### Safety & Disclaimer
Heating is a critical system. Do not use PumpSteer if your heating system is unstable or if you do not understand the behavior of virtual outdoor temperature manipulation.
