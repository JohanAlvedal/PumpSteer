# PumpSteer – Konfigurationsreferens

Detta dokument beskriver alla inställningar i PumpSteer, uppdelat i två delar:

- **[HA-gränssnitt](#ha-interface)** — reglage, switchar och entiteter du konfigurerar i Home Assistant
- **[settings.py](#settingspy)** — avancerade konstanter som kräver kodändring och omladdning av integrationen

-----

## HA-gränssnitt

### Setup (config flow)

Dessa sätts när du först lägger till integrationen. Du kan ändra dem senare via **Configure** i integrationssidan.

|Fält                                 |Beskrivning                                                                                                                        |
|-------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
|**Inomhustemperatursensor**          |Sensorn PumpSteer använder för aktuell inomhustemperatur. Måste vara en `sensor` med `device_class: temperature`.                 |
|**Utomhustemperatursensor**          |Den verkliga utomhustemperaturen. PumpSteer manipulerar denna signal innan den skickas till värmepumpen.                          |
|**Elprissensor**                     |Dagens tim- eller kvartstimmepris (t.ex. Nordpool). Måste ha attributet `today` eller `raw_today` med en lista av priser.         |
|**Elprissensor imorgon**             |Priser för morgondagen. Används för lookahead-bromsning och förvärmning.                                                           |
|**Väderentitet** *(valfri)*          |En `weather`-entitet som används för prognosbaserad förvärmning och förkylning. Lämna tom för att inaktivera prognosfunktioner.   |

-----

### Options (configure page)

Dessa kan ändras när som helst utan att starta om HA.

|Fält                                 |Beskrivning                                                                                                                      |Default|
|-------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|-------|
|**Notifikationstjänst** *(valfri)*   |Notifieringstjänst för prisvarningar, t.ex. `notify.mobile_app_my_phone`. Lämna tom för att använda HA persistent notifications.|—      |

-----

### Reglage (`number`-entiteter)

Finns på PumpSteer-enheten eller i din dashboard.

#### 🌡️ Målvärde temperatur

`number.pumpsteer_target_temperature` · Intervall: 16–27 °C · Steg: 0.5

Den inomhustemperatur PumpSteer försöker hålla. PI-regulatorn justerar den fejkade utetemperaturen för att styra värmepumpen mot detta mål.

**Exempel:**
- Högre värde = PumpSteer försöker hålla huset varmare
- Lägre värde = PumpSteer tillåter en svalare inomhustemperatur

-----

#### ☀️ Sommarläge tröskel

`number.pumpsteer_summer_mode_threshold` · Intervall: 10–30 °C · Steg: 0.5

När utomhustemperaturen når detta värde går PumpSteer in i **sommarläge** och slutar styra värmepumpen (skickar igenom den verkliga utetemperaturen oförändrad).

**Exempel:**
- Högre värde = sommarläge aktiveras senare
- Lägre värde = sommarläge aktiveras tidigare

-----

#### ⚡ Sparnivå

`number.pumpsteer_saving_level` · Intervall: 0–5 · Steg: 1

Styr hur aggressivt PumpSteer prioriterar besparing framför komfort under dyra prisperioder.

|Nivå |Beteende                                              |
|-----|------------------------------------------------------|
|0    |Prislogik avstängd — endast PI-reglering              |
|1    |Mycket försiktig, knappt märkbar                      |
|2    |Mild besparing                                        |
|3    |Balanserad *(rekommenderas)*                          |
|4    |Aggressiv besparing                                   |
|5    |Maximal besparing — märkbar temperatursänkning kan ske|

Vid nivå 0 är all prislogik avstängd. Vid högre nivåer bestämmer **comfort floor** (se `settings.py`) hur mycket temperaturen får sjunka innan bromsen släpper.

**Exempel:**
- Högre värde = mer besparing men större påverkan på komfort
- Lägre värde = stabilare komfort men mindre besparing

-----

#### 🏠 Bromsramp-tid

`number.pumpsteer_brake_ramp_time` · Intervall: 0.5–10.0 · Steg: 0.5

Styr hur lång tid det tar för bromsen att slå igenom fullt. Högre värde = mjukare och långsammare bromsning.

Ramp-tiden beräknas som:

```python
ramp_in  = max(RAMP_MIN, min(RAMP_MAX, value × RAMP_SCALE))
ramp_out = max(RAMP_MIN, ramp_in × 0.5)
````

Med standard `RAMP_SCALE = 10`:

| Slider-värde | Ramp in        | Ramp ut |
| ------------ | -------------- | ------- |
| 0.5–2.0      | 20 min *(min)* | 20 min  |
| 3.0          | 30 min         | 20 min  |
| 4.0          | 40 min         | 20 min  |
| 5.0          | 50 min         | 25 min  |
| 6.0+         | 60 min *(max)* | 30 min  |

> **Not:** Värden under 2.0 ger samma minimitid (20 min).

**Exempel:**

* Högre värde = bromsen byggs upp långsammare och mjukare
* Lägre värde = snabbare och mer direkt bromsning

---

### Switchar

#### 🔔 Notiser

`switch.pumpsteer_notifications`

Aktiverar eller inaktiverar pushnotiser när bromsning eller förvärmning startar.

#### 🏖️ Semesterläge

`switch.pumpsteer_holiday_mode`

Sänker måltemperaturen till `HOLIDAY_TEMP` (standard 16 °C). PI och bromslogik fortsätter fungera som vanligt.

---

## settings.py

Dessa inställningar kräver ändring i `custom_components/pumpsteer/settings.py` och omladdning av integrationen.

---

### Fake temperature limits

```python
MIN_FAKE_TEMP: Final[float] = -20.0
MAX_FAKE_TEMP: Final[float] = 25.0
```

Gränser för den fejkade utetemperaturen.

**Exempel:**

* Högre `MAX_FAKE_TEMP` = tillåter varmare signal
* Lägre `MAX_FAKE_TEMP` = begränsar uppåt
* Lägre `MIN_FAKE_TEMP` = tillåter kallare signal
* Högre `MIN_FAKE_TEMP` = begränsar nedåt

---

### Summer / precool

```python
PRECOOL_LOOKAHEAD: Final[int] = 24
PRECOOL_MARGIN: Final[float] = 3.0
```

**Exempel:**

* Högre LOOKAHEAD = mer framåtblick
* Lägre LOOKAHEAD = mer reaktivt
* Högre MARGIN = kräver varmare prognos
* Lägre MARGIN = triggar lättare

---

### PI controller

```python
PID_KP: Final[float] = 2.4
PID_KI: Final[float] = 0.035
PID_KD: Final[float] = 0.0
PID_INTEGRAL_CLAMP: Final[float] = 6.0
PID_OUTPUT_CLAMP: Final[float] = 12.0
```

**Exempel:**

* Högre KP = snabbare respons, mer risk för svängningar
* Lägre KP = mjukare respons
* Högre KI = starkare långsiktig korrigering
* Lägre KI = stabilare men långsammare
* Högre OUTPUT_CLAMP = större påverkan
* Lägre OUTPUT_CLAMP = begränsad påverkan

---

### Price classification

```python
PRICE_PERCENTILE_CHEAP: Final[float] = 30.0
PRICE_PERCENTILE_EXPENSIVE: Final[float] = 80.0
```

**Exempel:**

* Högre cheap = färre billiga timmar
* Lägre cheap = fler billiga timmar
* Lägre expensive = fler dyra timmar
* Högre expensive = färre dyra timmar

---

### Comfort floor

```python
COMFORT_FLOOR_BY_AGGRESSIVENESS: Final[List[float]] = [...]
```

**Exempel:**

* Högre värden = mer besparing
* Lägre värden = bättre komfort

---

### Brake strength

```python
BRAKE_DELTA_C: Final[float] = 10.0
```

**Exempel:**

* Högre värde = starkare broms
* Lägre värde = svagare broms

---

### Ramp timing

```python
RAMP_SCALE: Final[float] = 10.0
RAMP_MIN_MINUTES: Final[float] = 20.0
RAMP_MAX_MINUTES: Final[float] = 60.0
```

**Exempel:**

* Högre SCALE = större effekt av reglaget
* Högre MAX = mjukare system möjligt

---

### Preheating

```python
PREHEAT_BOOST_C: Final[float] = 4.0
```

**Exempel:**

* Högre värde = mer förvärmning
* Lägre värde = försiktigare

---

### Peak filter

```python
PEAK_FILTER_MIN_DURATION_MINUTES: Final[int] = 30
```

**Exempel:**

* Högre värde = ignorerar fler korta toppar
* Lägre värde = reagerar snabbare

---

### Price lookahead

```python
PRICE_LOOKAHEAD_HOURS: Final[int] = 6
```

**Exempel:**

* Högre värde = mer planering
* Lägre värde = mer reaktivt

---

### Brake hold time

```python
BRAKE_HOLD_MINUTES: Final[float] = 30.0
```

**Exempel:**

* Högre värde = broms ligger kvar längre
* Lägre värde = släpper snabbare

---

### Preheating on missing forecast

```python
PREHEAT_ON_MISSING_FORECAST: Final[bool] = False
```

**Exempel:**

* True = mer aggressiv fallback
* False = säkrare beteende

---

### Holiday temperature

```python
HOLIDAY_TEMP: Final[float] = 16.0
```

**Exempel:**

* Högre värde = varmare semesterläge
* Lägre värde = mer energispar
