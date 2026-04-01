## ⚠️ Important – Not a Drop-in Upgrade

PumpSteer 2.0.0 is **not a minor update**.  
It is a **complete rewrite of the control system**.

👉 You should treat this as a **new integration version**, not just an upgrade.

### What this means

- ❌ Old dashboards will **not behave the same**
- ❌ Existing automations may **break or misbehave**
- ❌ Old helper-based setups are **no longer primary control**
- ❌ Price categories and logic are **completely changed**

---

### 🔄 Required after upgrade

You will likely need to:

- Rebuild or update your **Lovelace cards**
- Update all **automations using price categories**
- Verify **price sensor structure (today + tomorrow)**
- Reconnect automations to **new PumpSteer entities**
- Re-tune:
  - aggressiveness
  - inertia
  - target temperature

---

### 🧠 Behavior is different

Even with the same settings:

- Control is now **PI-based**
- Braking is **ramped and stateful**
- Forecast logic affects decisions
- System reacts more **smoothly but differently**

➡️ Do not expect identical behavior compared to 1.6.6

---

### ✅ Recommendation

If you want a safe transition:

1. Install 2.0.0
2. Run it in parallel (observe only)
3. Compare behavior over 24–48 hours
4. Then migrate fully

---

## ⚠️ Disclaimer

You use this integration at your own risk.

Heating is a critical system in your home, and incorrect settings may lead to:
- discomfort
- inefficient operation
- or potential system issues

❗ Do NOT use PumpSteer if your heating system is not functioning properly.

Only use PumpSteer if:
- you understand how it works
- you have verified it behaves correctly in your setup
- you actively monitor indoor temperature and system response after installation

---

## 🗃️ Recorder Requirement

PumpSteer relies on **raw electricity price history** stored in Home Assistant.

Requirements:
- At least **72 hours of data**
- Must be available in the **recorder**
- Long-term statistics are NOT used

⚠️ If recorder data is missing:
- price classification may fail
- system may enter safe mode
- behavior may be incorrect

---

## 🧪 Note

This is a hobby project built with the help of:
- ChatGPT
- GitHub Copilot
- and a lot of patience 🙂

Feedback, ideas, and contributions are always welcome.

---

## 🔗 Links

- 🔗 GitHub repository
- 🐞 Create Issue

---

## 📜 License

- Version ≥ v1.6.2 → **AGPL-3.0**
- Version ≤ v1.5.1 → **Apache 2.0**

© Johan Älvedal
