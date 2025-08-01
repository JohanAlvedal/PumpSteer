# PumpSteer

PumpSteer är en anpassad Home Assistant-integration för att dynamiskt optimera din värmepump genom att manipulera insignalen från utomhustemperatursensorn. Den låter dig spara energi och pengar genom att anpassa din uppvärmningsstrategi baserat på elpriser, inomhustemperatur, väderprognoser och termisk tröghet.

---

## ⚠️ Ansvarsfriskrivning

Jag är inte expert på programmering, energihantering eller automation. Denna setup är baserad på mina personliga erfarenheter och experiment. Jag kan inte garantera att den fungerar för alla, och jag tar inget ansvar för problem eller skador som kan uppstå vid användning av denna konfiguration eller kod.

**Använd den på egen risk och testa noggrant i din egen miljö.**

---

## ✅ Funktioner

* 🔧 Smart virtuell styrning av utomhustemperatur
* 🌡️ Dynamisk komfortstyrning med:

  * Inomhustemperatur
  * Målinomhustemperatur
  * Prognos för elpris
  * Temperaturprognos (kommaseparerad lista)
  * Termisk tröghet
* 💸 Elprisanpassning via Nordpool eller annan sensor
* 🧊 Bromsläge: minimerar uppvärmning vid höga priser
* ☀️ Sommarläge: inaktiverar all styrning vid varma temperaturer
* 🏝️ Semesterläge: tillfällig temperatursänkning under frånvaro
* 🤖 ML-analys: inlärning av hur huset reagerar (sessionsbaserat)
* 🔁 Autojustering av `house_inertia` (om aktiverad)
* 🧠 Rekommendationer för förbättrad balans komfort/besparing
* 🎛️ Finjustering via `input_number`, `input_text`, `input_boolean`, `input_datetime`
* 🖼️ Extra sensorer för UI-visualisering

> 💡 **Notis:** Semesterläge är endast aktivt när utomhustemperaturen är under sommartröskeln.

---

## 🔧 Installation via HACS (Custom Repository)

Om PumpSteer ännu inte finns i HACS:

1. Gå till **HACS > ⋮ > Custom Repositories**
2. Lägg till: `https://github.com/JohanAlvedal/PumpSteer`
3. Välj **Integration** som kategori
4. Installera PumpSteer
5. Starta om Home Assistant
6. Följ installationsguiden och välj hjälpentiteter

---

## 📦 Hjälpentiteter (via `pumpsteer_package.yaml`)

| Typ              | Entitet                         | Funktion                                    |
| ---------------- | ------------------------------- | ------------------------------------------- |
| `input_number`   | `indoor_target_temperature`     | Mål för inomhustemperatur                   |
| `input_number`   | `pumpsteer_summer_threshold`    | Tröskel för att aktivera sommarläge         |
| `input_number`   | `pumpsteer_aggressiveness`      | Komfort vs besparing (0–5)                  |
| `input_number`   | `house_inertia`                 | Hur trögt huset reagerar (0–10)             |
| `input_text`     | `hourly_forecast_temperatures`  | Temperaturprognos (24 CSV-värden)           |
| `input_boolean`  | `holiday_mode`                  | Aktiverar semesterläge                      |
| `input_boolean`  | `autotune_inertia`              | Tillåt systemet att justera `house_inertia` |
| `input_datetime` | `holiday_start` / `holiday_end` | Automatisk aktivering av semesterläge       |

---

## 🧪 Prognosformat

`input_text.hourly_forecast_temperatures` måste innehålla exakt 24 kommaseparerade temperaturvärden (°C):

```
-3.5,-4.2,-5.0,-4.8,… (totalt 24 värden)
```

Om formatet är ogiltigt loggas ett fel och prognosen ignoreras.

---

## 📊 Sensor: `sensor.pumpsteer`

Denna sensor är integrationens huvudutgång.

### Tillstånd:

Virtuell (fejkad) utomhustemperatur som skickas till din värmepump.

### Attribut:

| Attribut                     | Betydelse                                              |
| ---------------------------- | ------------------------------------------------------ |
| `Mode`                       | `heating`, `neutral`, `braking_mode`, `summer_mode`    |
| `Fake Outdoor Temperature`   | Den beräknade temperatur som skickas till värmepumpen  |
| `Price Category`             | Klassificering av nuvarande elpris                     |
| `Status`                     | Systemstatus, t.ex. "OK" eller felmeddelanden          |
| `Current Price`              | Aktuellt elpris i SEK/kWh                              |
| `Max Price`                  | Dagens högsta elpris                                   |
| `Aggressiveness`             | Komfort kontra besparing (0–5)                         |
| `Inertia`                    | Husets uppskattade tröghet                             |
| `Target Temperature`         | Önskad inomhustemperatur                               |
| `Indoor Temperature`         | Faktisk innetemperatur                                 |
| `Outdoor Temperature`        | Verklig utomhustemperatur                              |
| `Summer Threshold`           | Tröskel för sommarläge                                 |
| `Braking Threshold (%)`      | Procentuellt tröskelvärde för att bromsa vid högt pris |
| `Price Factor (%)`           | Förhållandet mellan aktuellt och maxpris               |
| `Holiday Mode`               | Om semesterläge är aktivt                              |
| `Last Updated`               | Senaste uppdateringstiden                              |
| `Temp Error (°C)`            | Avvikelse från målinomhustemperatur                    |
| `To Summer Threshold (°C)`   | Hur nära det är till att aktivera sommarläge           |
| `Next 3 Hours Prices`        | Kommande elpriser                                      |
| `Saving Potential (SEK/kWh)` | Skillnad mellan maxpris och nuvarande pris             |
| `Decision Reason`            | Beskrivning av beslut bakom aktuell drift              |
| `Price Categories All Hours` | Klassificering för alla timmar                         |
| `Current Hour`               | Aktuell timme                                          |
| `Data Quality`               | Information om tillgänglighet och datamängd            |

---

## 🧠 Sensor: `sensor.pumpsteer_ml_analysis`

ML-sensor som visar analys och rekommendationer baserat på hur huset presterar.

### Attribut:

| Attribut                   | Beskrivning                                        |
| -------------------------- | -------------------------------------------------- |
| `success_rate`             | Hur ofta systemet träffade måltemp inom rimlig tid |
| `avg_heating_duration`     | Snittlängd på uppvärmningssessioner (min)          |
| `most_used_aggressiveness` | Vanligast använda aggressivitetsnivå               |
| `total_heating_sessions`   | Totalt antal identifierade sessioner               |
| `recommendations`          | Lista med textförslag baserat på prestanda         |
| `auto_tune_active`         | Om autojustering av `house_inertia` är aktiv       |
| `last_updated`             | Tidpunkt för senaste analysuppdatering             |

Rekommendationer visas i UI eller i `markdown`-kort.

---

## 🧠 Hur det fungerar

PumpSteer försöker styra värmepumpens uppfattade behov via fejkad utetemperatur:

* Värma mer när elpriset är lågt
* Undvika värme när priset är högt
* Gå i neutralt läge om allt är stabilt
* Stänga av värme vid hög utetemp (sommarläge)
* Sänka måltemperaturen till 16 °C under semester
* Lära sig över tid hur trögt huset är och anpassa inställningar (om `autotune_inertia` är aktivt)

All styrning sker helt lokalt utan molnberoenden.

---

## 🛠️ Loggning

* Fel och varningar loggas i Home Assistant
* Sensor visar `unavailable` vid saknade data
* ML-data sparas i `pumpsteer_ml_data.json` (max 100 sessions)
* Autojusterat `inertia` sparas i `adaptive_state.json`

---

## 🧪 Observera

Detta är ett hobbyprojekt byggt med hjälp av ChatGPT, Copilot och mycket tålamod. Feedback, förbättringar och förslag är alltid välkomna.

---

## 🔗 Länkar

* 🔗 [GitHub-repo](https://github.com/JohanAlvedal/PumpSteer)
* 🐞 [Skapa Issue](https://github.com/JohanAlvedal/PumpSteer/issues)

---

© Johan Älvedal
