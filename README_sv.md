# 🔥 PumpSteer 2.0.0

➡️ English version: [README](README.md)

> ⚠️ Detta är en större omskrivning. Läs uppgraderingsguiden innan installation.

PumpSteer är en Home Assistant custom integration som optimerar din värmepump genom att dynamiskt justera den **virtuella utomhustemperaturen**.

Den minskar energikostnaden när elen är dyr — samtidigt som komforten inomhus bibehålls.

---

## 📘 Dokumentation

- [Varning vid uppgradering](#important--inte-en-drop-in-uppgradering-)
- [Nyheter i 2.0.0](#whats-new-in-200)
- [Breaking Changes](#breaking-changes)
- [Elprissensor](#price-sensor-support)
- [Väderstöd](#weather-support)
- [Ny installation](#new-installation)
- [Dashboard (Lovelace)](#lovelace-dashboard-mini-graph-card)
- [Uppgradering från 1.6.6](#upgrade-from-166)
- [Felsökning](#troubleshooting)
- [Trimning](#tuning-quick-guide)
- [Säkerhet](#safety--disclaimer)

---

## Important – Inte en drop-in uppgradering ⚠️

PumpSteer 2.0.0 är **inte en mindre uppdatering**.  
Det är en **total omskrivning av styrningen**.

👉 Se detta som en **ny integration**, inte en uppgradering.

### Vad detta innebär

- ❌ Gamla dashboards beter sig annorlunda  
- ❌ Automationer kan sluta fungera  
- ❌ Gamla helpers används inte längre som primär styrning  
- ❌ Elprislogiken är helt omgjord  

---

### Krävs efter uppgradering

- Bygg om Lovelace-kort  
- Uppdatera automationer  
- Verifiera elpriser (idag + imorgon)  
- Koppla om till nya entiteter  
- Trimma inställningar  

---

### Beteendet är förändrat

- PI-reglering istället för heuristik  
- Mjuk bromsning (ramp)  
- Prognosbaserade beslut  

➡️ Förvänta dig inte samma beteende som 1.6.6

---

### Rekommendation

1. Installera 2.0.0  
2. Observera i 24–48 timmar  
3. Migrera fullt därefter  

---

## What's New in 2.0.0

- 🧠 PI-baserad reglering (ersätter heuristik)
- ⚡ Smart prisindelning (`cheap / normal / expensive`)
- 🔁 Tillståndsmaskin (förutsägbart beteende)
- 🧊 Dynamisk bromsning (ramp + hold + filtrering)
- 🌦 Prognosbaserad styrning (valbar)
- 🏠 Integration hanterar egna entiteter
- 🔒 Körs helt lokalt

---

## Breaking Changes

### Prisnivåer ändrade

Tidigare:
- `very_cheap`
- `very_expensive`
- `extreme`

Nu:
- `cheap`
- `normal`
- `expensive`

---

### Krav på elprissensor

Måste stödja:
- `today/raw_today`
- `tomorrow/raw_tomorrow`

---

### Styrsystem omskrivet

- Tidigare: heuristik  
- Nu: PI + state machine  

---

### Bromsning omgjord

- rampning
- hold-logik
- peak-filtrering
- komfortskydd

---

### Integration äger entiteter

- number
- switch
- datetime

---

### ML borttaget

- används inte längre i runtime

---

## Elprissensor

Stödda format:

- `0.95`
- `"0.95"`
- `{ "value": 0.95 }`
- `{ "price": 0.95 }`

📌 Rekommenderat exempel:

[`other/nordpool.yaml`](other/nordpool.yaml)

✔ Fungerar med:
- Officiella Nord Pool-integrationen
- PumpSteer 2.0.0

---

## Väderstöd

Exempel:
- `weather.smhi_home`
- `weather.yr_home`

⚠️ Måste väljas i:  
Inställningar → Enheter & Tjänster → PumpSteer → Konfigurera

---

## Ny installation

### Steg-för-steg

1. Installera via HACS eller manuellt  
2. Starta om Home Assistant  
3. Lägg till integration  
4. Välj sensorer  

---

### Första kontroll

- `sensor.pumpsteer` aktiv  
- `status = ok`  
- `price_category` ändras  
- `mode` beter sig logiskt  

---

## 📊 Lovelace Dashboard (mini-graph-card)

📁 Se [`/dashboards/`](dashboards/) för färdiga exempel

PumpSteer innehåller exempel på Lovelace-konfigurationer med `mini-graph-card`.

---

### ⚠️ Krav

Installera:

- **mini-graph-card** via HACS

---

### 📥 Så använder du mallarna

1. Gå till din dashboard  
2. Klicka på **Redigera dashboard**  
3. Klicka på **pennan (✏️)** på vyn  
4. Klicka på **tre prickar (⋮)** uppe till höger  
5. Välj **Redigera i YAML**  
6. Klistra in koden  
7. Spara  

⚠️ OBS:  
Detta kan ersätta hela vyn – ta backup först.

---

### Viktigt

- Detta är **YAML**, inte klickbara kort  
- Du kan behöva ändra entitetsnamn  

---

## Uppgradering från 1.6.6

### Krävs

- Uppdatera prisnivåer  
- Lägg till morgondagens pris  
- Uppdatera automationer  
- Ta bort ML  

---

### Rekommenderas

- Kontrollera prisdata  
- Lägg till väderentitet  
- Uppdatera holiday-logik  

---

### Testa

- Kontrollera `mode`  
- Kontrollera `brake_factor`  
- Se beteende vid dyr el  

---

## Felsökning

### Safe mode

Orsak:
- saknar prisdata  

Åtgärd:
- kontrollera `today/raw_today`
- kontrollera `tomorrow/raw_tomorrow`

---

## Trimning

### Aggressivitet

- 0 → ingen prisstyrning  
- 1–2 → mild  
- 3–4 → balanserad  
- 5 → aggressiv  

---

## Säkerhet

Använd på egen risk.

Övervaka alltid:
- innetemperatur
- systemets beteende

---

© Johan Älvedal
