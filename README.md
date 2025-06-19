
<p align="center">
  <img src="https://github.com/JohanAlvedal/VirtualOutdoorTemp/raw/main/custom_components/virtualoutdoortemp/icons/icon.png" alt="VirtualOutdoorTemp Logo" width="400">
</p>

# 🌡️ VirtualOutdoorTemp – Smarter Heating via Virtual Temperature Control

**VirtualOutdoorTemp** is a Home Assistant custom integration that intelligently simulates outdoor temperature to steer your heating system based on electricity prices, weather forecasts, indoor conditions, and house inertia.

---

> 🧪 **Note:** This integration is a *Work In Progress* and actively being improved. Expect frequent updates and new features!

---

## 🚀 Features

✅ Simulates outdoor temperature to influence heat pump behavior  
✅ Adapts using indoor temp, electricity price, and weather forecast  
✅ "Aggressiveness" slider lets you control energy-saving intensity  
✅ Boost mode pre-heats when electricity is cheap  
✅ Learns your house's thermal inertia over time  
✅ Summer mode bypasses control above a temperature threshold  
✅ Clean dashboard with ApexCharts integration  
✅ Fully local – no cloud dependency  
✅ Easy configuration via UI  

---

## 🛠 Installation

1. Copy the `virtualoutdoortemp` folder to your `config/custom_components/` directory.

```bash
/config/custom_components/virtualoutdoortemp/
```

2. **Restart Home Assistant** after installing the integration.

3. Go to **Settings → Devices & Services → Add Integration → VirtualOutdoorTemp**

4. Select your indoor temperature sensor, outdoor sensor, price sensor etc.

ℹ️ *Note: Some sensors may show `n/a` or be missing from charts initially — wait a few minutes for history to build up.*

---

## ⚙️ Additional Setup Required

This integration also relies on helpers and templates. You need to:

1. **Manually copy the file** `packages/virtualoutdoortemp.yaml` into your Home Assistant `/config/packages/` folder  
2. Make sure this is in your `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

3. **Manually add the UI elements to your Lovelace dashboard**  
   - You can use the example dashboard configuration in this repository  
   - ApexCharts card is recommended (available via HACS)

---

## 📊 Lovelace Dashboard

Use the included ApexCharts template and entity cards to show:

- Virtual vs real outdoor temp
- Heating mode (neutral, balance, boost)
- Energy price and heating aggressiveness
- Live difference to target temp

---

## 🧠 Learning Mode

The system gradually adjusts based on how fast your house heats up or cools down, thanks to the optional `house_inertia` automation template.

---

## 💬 Support & Feedback

- GitHub: [JohanAlvedal/VirtualOutdoorTemp](https://github.com/JohanAlvedal/VirtualOutdoorTemp)
- Issues: [Open an issue](https://github.com/JohanAlvedal/VirtualOutdoorTemp/issues)

---

Enjoy smarter heating – with less hassle and lower cost!
