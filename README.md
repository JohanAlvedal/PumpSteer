# 🔥 PumpSteer 2.X – Smart Heat Pump Optimization

➡️ Swedish version: [README (Svenska)](README_sv.md)

> ⚠️ **Major rewrite.** Please read the [Installation & Upgrade Guide](docs/INSTALLATION.md) before installing.

PumpSteer is a Home Assistant custom integration that optimizes your heat pump by dynamically adjusting the **virtual outdoor temperature**. 

It reduces energy costs during peak price hours while maintaining indoor comfort through intelligent PI-control.

<a href="https://www.buymeacoffee.com/alvjo" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px !important;width: 200px !important;">
</a>

---

## 📸 Dashboard Preview

<table>
  <tr>
    <td><img src="docs/img/01.png" width="200"/></td>
    <td><img src="docs/img/02.png" width="200"/></td>
    <td><img src="docs/img/03.png" width="200"/></td>
  </tr>
</table>

---

## 📘 Documentation

To keep things organized, the documentation is divided into the following sections:

### 🚀 Getting Started
* **[Installation Guide](docs/INSTALLATION.md)** – Step-by-step setup and upgrade notes from v1.6.6.
* **[Configuration](docs/Configuration.md)** – Detailed explanation of all integration settings.
* **[Dashboard Setup](docs/DASHBOARD.md)** – How to use the provided Lovelace templates.

### 🧠 Deep Dive
* **[System Architecture](docs/ARCHITECTURE.md)** – How the PI-control and state machine works.
* **[Tuning Guide](docs/TUNING.md)** – How to optimize Inertia and Aggressiveness for your home.
* **[Decisions & Logic](docs/DECISIONS.md)** – The reasoning behind the control strategies.

### 🛠 Support & Future
* **[Troubleshooting](docs/TROUBLESHOOTING.md)** – Common issues and how to fix them.
* **[Changelog](docs/CHANGELOG.md)** – Version history and updates.
* **[Roadmap](docs/ROADMAP.md)** – Planned features and future development.

---

## 🔧 How it works

PumpSteer calculates a **virtual outdoor temperature** based on electricity prices, indoor temperature, and weather forecasts. 

It pushes this value to hardware (like an **Ohmigo** device) connected to your heat pump's outdoor sensor. The heat pump "sees" a different temperature and adjusts its performance accordingly—saving you money without needing complex Modbus or Cloud APIs.

---

## ⚠️ Disclaimer

You use this integration at your own risk. Heating is a critical system in your home. Incorrect settings may lead to discomfort or potential damage. Always monitor your system behavior closely after installation.

---

## 🔗 Links
- 🐞 [Report a Bug / Feature Request](https://github.com/JohanAlvedal/PumpSteer/issues)
- 📝 License: AGPL-3.0
- © Johan Älvedal
