# 🔥 PumpSteer 2.0.0

➡️ Swedish version: [README (Svenska)](#-pumpsteer-200-svenska)

PumpSteer is a Home Assistant custom integration that optimizes your heat pump by dynamically adjusting the **virtual outdoor temperature**.

It reduces energy cost when electricity is expensive — while protecting indoor comfort.

---

## 🚀 What's New in 2.0.0

PumpSteer 2.0.0 is a **major rewrite** of the control system.

### ✨ Highlights

- 🧠 **PI-based control (replaces heuristics)**
- ⚡ **Smart price classification (`cheap / normal / expensive`)**
- 🔁 **State machine (predictable behavior)**
- 🧊 **Dynamic braking (ramp + hold + filtering)**
- 🌦 **Forecast-aware planning (optional)**
- 🏠 **Integration-managed entities**
- 🔒 **Fully local (no cloud)**

---

## ⚠️ Breaking Changes

### 💸 Price categories changed

Old:
- `very_cheap`, `very_expensive`, `extreme` ❌

New:
- `cheap`, `normal`, `expensive` ✅

👉 Update all automations/templates

---

### 📊 Price sensor requirements

PumpSteer now requires **structured price data**:

- `today` / `raw_today`
- `tomorrow` / `raw_tomorrow`

You must configure:
- `electricity_price_entity`
- `price_tomorrow_entity`

---

### 🎛 Control system rewritten

- Old: heuristic logic  
- New: **PI controller + state machine**

➡️ More stable, but different behavior

---

### 🧱 Braking redesigned

Now includes:
- ramping (no instant jumps)
- hold over short dips
- peak filtering
- comfort protection

---

### ⚙️ Integration now owns entities

PumpSteer creates:
- Number entities (target, aggressiveness, inertia)
- Switch (holiday)
- Datetime (holiday start/end)

➡️ Old helpers are no longer primary control

---

### 🤖 ML removed

- Old ML features are no longer active
- Clean, stable core is prioritized

---

## ⚡ Price Sensor Support

Supported formats:
- `0.95`
- `"0.95"`
- `{ "value": 0.95 }`
- `{ "price": 0.95 }`

📌 Recommended example:

other/nordpool.yaml


✔ Works with:
- Official Nord Pool integration
- PumpSteer 2.0.0

---

## 🌦 Weather Support (Optional)

Examples:
- `weather.smhi_home`
- `weather.yr_home`

⚠️ Must be selected in:
**Settings → Devices → PumpSteer → Configure**

---

# 📘 Wiki – Installation & Upgrade

---

## 🆕 New Installation

### Step-by-step

1. Install via HACS or manually  
2. Restart Home Assistant  
3. Add integration  
4. Select:
   - indoor temperature
   - outdoor temperature
   - electricity price (today)
   - electricity price (tomorrow)
   - optional weather entity  

### ✅ Verify after 10–30 minutes

- `sensor.pumpsteer` = active
- `status = ok`
- `price_category` changes
- `mode` changes logically

---

## 🔄 Upgrade from 1.6.6

### 🔴 Must update

- Replace old price categories
- Configure tomorrow price entity
- Update automations
- Remove ML references

---

### 🟡 Should verify

- Price attributes exist
- Weather entity selected (optional)
- Holiday automations updated

---

### 🧪 Test after upgrade

- Check `mode`
- Check `brake_factor`
- Observe one expensive period

---

## 🛠 Common Issues

### ❌ Safe mode

Cause:
- missing price data
- invalid sensor

Fix:
- check `today/raw_today`
- check `tomorrow/raw_tomorrow`

---

### ❌ No braking

Cause:
- not `expensive`
- comfort protection active

---

### ❌ Wrong price category

Cause:
- bad price format

---

## 🧾 Summary

PumpSteer 2.0.0 introduces:

- PI-based control  
- state machine  
- smarter braking  
- standardized price logic  
- cleaner architecture  

➡️ More stable, smarter, and ready for future features
