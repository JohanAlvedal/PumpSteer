# 🔥 PumpSteer 2.0.0 (Svenska)

➡️ English version: [README (English)](#-pumpsteer-200)

PumpSteer är en Home Assistant-integration som optimerar din värmepump genom att justera den **virtuella utomhustemperaturen**.

Den minskar energikostnader när elen är dyr – utan att försämra komforten.

---

## 🚀 Nyheter i 2.0.0

Detta är en **stor ombyggnad** av hela styrlogiken.

### ✨ Höjdpunkter

- 🧠 **PI-reglering (ersätter heuristik)**
- ⚡ **Elprisklasser: `cheap / normal / expensive`**
- 🔁 **Tydlig state machine**
- 🧊 **Mjuk bromsning (ramp + hold)**
- 🌦 **Prognosbaserad styrning (valfri)**
- 🏠 **Integration skapar egna entiteter**
- 🔒 **Helt lokal drift**

---

## ⚠️ Breaking Changes

### 💸 Nya priskategorier

Gamla:
- `very_cheap`, `very_expensive`, `extreme`

Nya:
- `cheap`, `normal`, `expensive`

---

### 📊 Nya krav på elpriser

Måste ha:
- `today/raw_today`
- `tomorrow/raw_tomorrow`

---

### 🎛 Ny styrning

- Tidigare: heuristik  
- Nu: **PI + state machine**

---

### 🧱 Ny bromslogik

- mjuk ramp
- hold över korta dippar
- filtrering av toppar
- komfortskydd

---

### ⚙️ Egna entiteter

PumpSteer skapar:
- nummer
- switch
- datetime

---

## 📘 Wiki

---

### 🆕 Ny installation

1. Installera  
2. Starta om HA  
3. Lägg till integration  
4. Välj sensorer  

---

### 🔄 Uppgradering

Du måste:

- uppdatera automations
- fixa prissensor
- ta bort ML

---

### 🧪 Test

- kontrollera `mode`
- kontrollera `price_category`
- kontrollera broms

---

## 🧾 Sammanfattning

PumpSteer 2.0.0 är:

- smartare  
- stabilare  
- tydligare  

➡️ redo för framtiden
