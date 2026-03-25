 🔥 PumpSteer 2.0.0 (Svenska)

➡️ English version: [README (English)](#pumpsteer-200)

> ⚠️ Detta är en stor omskrivning. Läs uppgraderingsguiden innan installation.

PumpSteer är en Home Assistant-integration som optimerar din värmepump genom att justera den **virtuella utomhustemperaturen**.

Den minskar energikostnader när elen är dyr — utan att försämra inomhuskomforten.

---

## 📘 Dokumentation

- [Viktig information om uppgradering](#important--not-a-drop-in-upgrade)
- [Nyheter i 2.0.0](#whats-new-in-200)
- [Breaking Changes](#breaking-changes)
- [Elprissensor](#price-sensor-support)
- [Väderstöd](#weather-support)
- [Ny installation](#new-installation)
- [Uppgradering från 1.6.6](#upgrade-from-166)
- [Felsökning](#troubleshooting)
- [Inställningar (Tuning)](#tuning-quick-guide)
- [Säkerhet](#safety--disclaimer)

---

## Important – Not a Drop-in Upgrade ⚠️

PumpSteer 2.0.0 är **inte en mindre uppdatering**.  
Det är en **helt ny version av styrlogiken**.

👉 Se detta som en **ny installation**, inte en uppgradering.

### Vad betyder det?

- ❌ Gamla dashboards fungerar inte likadant  
- ❌ Automations kan sluta fungera  
- ❌ Gamla helpers styr inte längre systemet  
- ❌ Elprislogiken är helt förändrad  

---

### Vad du behöver göra efter uppgradering

- Bygga om Lovelace-kort  
- Uppdatera automations  
- Kontrollera elprissensor (today + tomorrow)  
- Koppla om till nya PumpSteer-entiteter  
- Justera inställningar  

---

### Beteendet är annorlunda

- PI-reglering istället för heuristik  
- Mjuk bromsning (ramp)  
- Prognos påverkar beslut  

➡️ Förvänta dig inte samma beteende som 1.6.6

---

### Rekommendation

1. Installera 2.0.0  
2. Observera i 24–48 timmar  
3. Migrera fullt därefter  

---

## What's New in 2.0.0

- 🧠 PI-reglering (ersätter heuristik)
- ⚡ Elprisklasser (`cheap / normal / expensive`)
- 🔁 State machine (förutsägbart beteende)
- 🧊 Smart bromsning (ramp + hold + filtrering)
- 🌦 Prognosbaserad styrning (valfri)
- 🏠 Integration skapar egna entiteter
- 🔒 Helt lokal drift

---

## Breaking Changes

### Elpriskategorier ändrade

Gamla:
- `very_cheap`, `very_expensive`, `extreme`

Nya:
- `cheap`, `normal`, `expensive`

---

### Krav på elprissensor

Måste stödja:
- `today/raw_today`
- `tomorrow/raw_tomorrow`

---

### Ny styrlogik

- Tidigare: heuristik  
- Nu: PI + state machine  

---

### Ny bromslogik

- rampning
- hold över korta dippar
- filtrering av toppar
- komfortskydd

---

### Integration skapar egna entiteter

- number
- switch
- datetime

---

### ML borttaget

- används inte längre i runtime

---

## Price Sensor Support

Stödda format:

- `0.95`
- `"0.95"`
- `{ "value": 0.95 }`
- `{ "price": 0.95 }`

📌 Rekommenderat exempel:


other/nordpool.yaml


✔ Fungerar med:
- Officiella Nord Pool-integrationen
- PumpSteer 2.0.0

---

## Weather Support

Exempel:
- `weather.smhi_home`
- `weather.yr_home`

⚠️ Måste väljas i:
Inställningar → Enheter → PumpSteer → Konfigurera

---

## New Installation

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

## Upgrade from 1.6.6

### Måste göras

- Uppdatera priskategorier  
- Lägg till tomorrow-pris  
- Uppdatera automations  
- Ta bort ML  

---

### Bör kontrolleras

- Elprisdata finns  
- Väder är konfigurerat  
- Holiday automations  

---

### Test

- Kontrollera `mode`
- Kontrollera `brake_factor`
- Följ en dyr period

---

## Troubleshooting

### Safe mode

Orsak:
- saknad prisdata

Lösning:
- kontrollera `today/raw_today`
- kontrollera `tomorrow/raw_tomorrow`

---

### Ingen bromsning

Orsak:
- ej `expensive`
- komfortskydd aktivt

---

### Fel priskategori

Orsak:
- fel dataformat

---

## Tuning (Quick Guide)

### Aggressivitet

- 0 → ingen prisstyrning  
- 1–2 → mild  
- 3–4 → balanserad  
- 5 → aggressiv  

---

### Tröghet (inertia)

- Låg → snabb respons  
- Hög → långsam respons  

Typiskt:
- Lägenhet → låg  
- Hus → medel  
- Tungt hus → hög  

---

## Safety & Disclaimer

Du använder denna integration på egen risk.

Uppvärmning är ett kritiskt system.

Använd inte om:
- systemet är instabilt
- du inte förstår hur det fungerar

Övervaka alltid:
- inomhustemperatur
- systemets beteende

---

## Recorder Requirement

Kräver:
- minst 72 timmars elprisdata
- lagrat i recorder

Om detta saknas:
- klassificering kan misslyckas
- systemet kan gå i safe mode

---

## Note

Detta är ett hobbyprojekt byggt med:
- ChatGPT
- Copilot
- tålamod 🙂

Feedback välkomnas!

---

## Links

- GitHub repository  
- Create Issue  

---

## License

- ≥ v1.6.2 → AGPL-3.0  
- ≤ v1.5.1 → Apache 2.0  

© Johan Älvedal
