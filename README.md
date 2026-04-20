# 🔥 PumpSteer – Smart Heat Pump Optimization

➡️ Swedish version: [README (Svenska)](README_sv.md)

PumpSteer is a Home Assistant custom integration that optimizes your heat pump by dynamically adjusting the **virtual outdoor temperature**.

It reduces energy costs during peak price hours while maintaining indoor comfort through intelligent PI-control.

<a href="https://www.buymeacoffee.com/alvjo" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px !important;width: 200px !important;">
</a>

---

## 📘 Documentation

Full documentation is available at **[johanalvedal.github.io/PumpSteer](https://johanalvedal.github.io/PumpSteer/)**

### 🚀 Getting Started
* **[Installation Guide](https://johanalvedal.github.io/PumpSteer/INSTALLATION)** – Step-by-step setup and upgrade notes.
* **[Configuration](https://johanalvedal.github.io/PumpSteer/Configuration)** – Detailed explanation of all integration settings.
* **[Dashboard Setup](https://johanalvedal.github.io/PumpSteer/DASHBOARD)** – How to use the provided Lovelace templates.

### 🧠 Deep Dive
* **[System Architecture](https://johanalvedal.github.io/PumpSteer/ARCHITECTURE)** – How the PI-control and state machine works.
* **[Tuning Guide](https://johanalvedal.github.io/PumpSteer/TUNING)** – How to optimize Inertia and Aggressiveness for your home.
* **[Design Decisions](https://johanalvedal.github.io/PumpSteer/DECISIONS)** – The reasoning behind the control strategies.

### 🛠 Support & Future
* **[Troubleshooting](https://johanalvedal.github.io/PumpSteer/TROUBLESHOOTING)** – Common issues and how to fix them.
* **[Changelog](https://johanalvedal.github.io/PumpSteer/CHANGELOG)** – Version history and updates.
* **[Roadmap](https://johanalvedal.github.io/PumpSteer/ROADMAP)** – Planned features and future development.

---

## 🔧 How it works

PumpSteer calculates a **virtual outdoor temperature** based on electricity prices, indoor temperature, and weather forecasts.

It pushes this value to hardware (like an **Ohmigo** device) connected to your heat pump's outdoor sensor. The heat pump "sees" a different temperature and adjusts its performance accordingly — saving you money without needing complex Modbus or Cloud APIs.

---

## ⚠️ Disclaimer

You use this integration at your own risk. Heating is a critical system in your home. Incorrect settings may lead to discomfort or potential damage. Always monitor your system behavior closely after installation.

---

## 🔗 Links
- 📖 [Documentation](https://johanalvedal.github.io/PumpSteer/)
- 🐞 [Report a Bug / Feature Request](https://github.com/JohanAlvedal/PumpSteer/issues)
- 📝 License: AGPL-3.0
- © Johan Älvedal
