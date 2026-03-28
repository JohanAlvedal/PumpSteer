# PumpSteer – Konfigurationsreferens

Det här dokumentet beskriver alla inställningar i PumpSteer, uppdelat i två delar:

- **[HA-gränssnittet](#ha-gränssnittet)** — sliders, switchar och entitetsväljare du konfigurerar i Home Assistant
- **[settings.py](#settingspy)** — avancerade konstanter som kräver en kodändring och omladdning av integrationen

-----

## HA-gränssnittet

### Installation (config flow)

Dessa ställs in en gång när du lägger till integrationen. Du kan ändra dem senare via **Konfigurera** på integrationssidan.

|Fält                         |Beskrivning                                                                                                                           |
|-----------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
|**Inomhustemperatursensor**  |Sensorn PumpSteer läser för aktuell inomhustemperatur. Måste vara en `sensor` med `device_class: temperature`.                        |
|**Utomhustemperatursensor**  |Den riktiga utomhustemperatursensorn. PumpSteer manipulerar den här signalen innan den skickas till värmepumpen.                      |
|**Elprissensor**             |Dagens tim- eller kvartsvisa spotprissensor (t.ex. Nordpool). Måste ha ett `today`- eller `raw_today`-attribut med en lista av priser.|
|**Morgondagens elprissensor**|Morgondagens prissensor. Används för förutseende bromsning och förvärmning.                                                           |
|**Väderentitet** *(valfri)*  |En `weather`-entitet för prognosbaserad förvärmning och förkylning. Lämna tomt för att inaktivera prognos-funktioner.                 |

-----

### Alternativ (konfigurera-sidan)

Dessa kan ändras när som helst utan att starta om HA.

|Fält                           |Beskrivning                                                                                                                                  |Standard|
|-------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|--------|
|**Aviseringstjänst** *(valfri)*|Aviseringstjänst för prisvarningar, t.ex. `notify.mobile_app_my_phone`. Lämna tomt för att använda HA:s inbyggda notifieringar i sidopanelen.|—       |

-----

### Sliders (`number`-entiteter)

Finns på PumpSteer-enhetssidan eller i ditt dashboard.

#### 🌡️ Måltemperatur

`number.pumpsteer_target_temperature` · Område: 16–27 °C · Steg: 0.5

Den inomhustemperatur PumpSteer försöker hålla. PI-regulatorn justerar den falska utomhustemperaturen för att styra värmepumpen mot detta mål.

-----

#### ☀️ Sommarlägeströskel

`number.pumpsteer_summer_mode_threshold` · Område: 10–30 °C · Steg: 0.5

När utomhustemperaturen når det här värdet växlar PumpSteer till **sommarläge** och slutar styra värmepumpen (skickar igenom den riktiga utomhustemperaturen oförändrad).

-----

#### ⚡ Sparläge

`number.pumpsteer_saving_level` · Område: 0–5 · Steg: 1

Styr hur aggressivt PumpSteer prioriterar besparing framför komfort under dyra prisperioder.

|Nivå|Beteende                                                   |
|----|-----------------------------------------------------------|
|0   |Prisstyrning inaktiverad — ren PI-komfortstyrning          |
|1   |Mycket mild, knappt märkbar                                |
|2   |Mild besparing                                             |
|3   |Balanserad *(rekommenderad)*                               |
|4   |Aggressiv besparing                                        |
|5   |Maximal besparing — inomhustemperaturen kan sjunka märkbart|

På nivå 0 kopplas bromsen och all prislogik bort helt. På högre nivåer avgör **komfortgolvet** (se `settings.py`) hur långt inomhustemperaturen får sjunka innan bromsen släpps.

-----

#### 🏠 Bromsramptid

`number.pumpsteer_brake_ramp_time` · Område: 0.5–10.0 · Steg: 0.5

Styr hur lång tid bromsen tar på sig att engageras fullt. Högre värde = långsammare, mjukare övergång till bromsning.

Ramptiden beräknas som:

```
ramp_in  = max(RAMP_MIN, min(RAMP_MAX, värde × RAMP_SCALE))
ramp_out = max(RAMP_MIN, ramp_in × 0.5)
```

Med standard `RAMP_SCALE = 10`:

|Slidervärde|Ramp in           |Ramp out|
|-----------|------------------|--------|
|0.5–2.0    |20 min *(minimum)*|20 min  |
|3.0        |30 min            |20 min  |
|4.0        |40 min            |20 min  |
|5.0        |50 min            |25 min  |
|6.0+       |60 min *(maximum)*|30 min  |


> **Obs:** Värden under 2.0 ger alla minimaltiden eftersom `1 × 2.0 × 10 = 20 = RAMP_MIN`. Du behöver gå över 2.0 för att se någon skillnad.

-----

### Switchar

#### 🔔 Aviseringar

`switch.pumpsteer_notifications`

Aktiverar eller inaktiverar push-notiser när bromsning startar eller förvärmning börjar. Använder aviseringstjänsten konfigurerad under alternativ, eller HA:s inbyggda notifieringar om ingen tjänst är inställd.

#### 🏖️ Semesterläge

`switch.pumpsteer_holiday_mode`

Sänker måltemperaturen till `HOLIDAY_TEMP` (standard 16 °C). PI-regulatorn och bromslogiken fortsätter att köra normalt på den lägre måltemperaturen. Använd semester-start/slut-entiteterna för att schemalägga detta automatiskt.

-----

## settings.py

Dessa konstanter kräver att du redigerar `custom_components/pumpsteer/settings.py` och laddar om integrationen. De är avsedda för avancerad finjustering — standardvärdena är rimliga för de flesta installationer.

-----

### Gränser för falsk temperatur

```python
MIN_FAKE_TEMP: Final[float] = -20.0
MAX_FAKE_TEMP: Final[float] = 25.0
```

Hårda gränser för den falska utomhustemperaturen som skickas till värmepumpen. Om PI-regulatorn eller bromsberäkningen skulle överskrida dessa klipps värdet. Höj `MAX_FAKE_TEMP` något om din värmepump behöver en varmare signal i sommar- eller förkylningsläge.

-----

### Sommar / förkylning

```python
PRECOOL_LOOKAHEAD: Final[int] = 24    # timmar framåt att scanna för varm prognos
PRECOOL_MARGIN: Final[float] = 3.0   # °C över sommartröskel för att trigga förkylning
```

Förkylning aktiveras när någon prognos inom `PRECOOL_LOOKAHEAD` timmar överstiger `summer_threshold + PRECOOL_MARGIN`. Den höjer den falska utomhustemperaturen för att avskräcka värmepumpen från att värma inför sommaren.

-----

### PI-regulator

```python
PID_KP: Final[float] = 2.4       # proportionell förstärkning
PID_KI: Final[float] = 0.035     # integral förstärkning
PID_KD: Final[float] = 0.0       # derivata-förstärkning (lämna på 0 om du inte vet vad du gör)
PID_INTEGRAL_CLAMP: Final[float] = 6.0   # max uppbyggd integralkorrigering (°C)
PID_OUTPUT_CLAMP: Final[float] = 12.0    # max total PI-utsignal (°C)
```

PI-regulatorn håller inomhustemperaturen på målvärdet genom att justera den falska utomhustemperaturen. Högre `KP` = snabbare reaktion på aktuellt fel. Högre `KI` = starkare korrigering av långsiktig drift. Integralen fryses (återställs inte) under bromsning för att undvika ett stort värmeutbrott när bromsen släpper.

-----

### Prisklassificering

```python
PRICE_PERCENTILE_CHEAP: Final[float] = 30.0      # under P30 = billigt
PRICE_PERCENTILE_EXPENSIVE: Final[float] = 80.0  # över P80 = dyrt
DEFAULT_TRAILING_HOURS: Final[int] = 72           # historikfönster för percentiler
MIN_SAMPLES_FOR_CLASSIFICATION: Final[int] = 5
ABSOLUTE_CHEAP_LIMIT: Final[float] = 0.60        # alltid billigt under detta (SEK/kWh)
```

Priser klassificeras relativt de senaste 72 timmarna av historik. Percentilgränserna bestämmer billigt/normalt/dyrt-banden. `ABSOLUTE_CHEAP_LIMIT` åsidosätter percentilen — ett pris under detta är alltid billigt oavsett historik (användbart när alla senaste priser är låga).

-----

### Komfortgolv

```python
COMFORT_FLOOR_BY_AGGRESSIVENESS: Final[List[float]] = [
    0.0,  # nivå 0 — ingen prisstyrning
    0.5,  # nivå 1
    1.0,  # nivå 2
    1.5,  # nivå 3
    2.0,  # nivå 4
    3.0,  # nivå 5
]
```

Hur många °C under måltemperaturen som inomhustemperaturen får sjunka innan bromsen släpps, per sparläge. På nivå 3 med måltemperatur 21 °C släpps bromsen om inomhustemperaturen sjunker under 19,5 °C. Måste ha exakt 6 värden.

-----

### Bromsstyrka

```python
BRAKE_DELTA_C: Final[float] = 10.0
```

Under bromsning sätts den falska utomhustemperaturen till `utomhus + BRAKE_DELTA_C`. Detta får värmepumpen att tro att det är varmare ute än det är, vilket minskar värmeeffekten. Högre värde = starkare bromsning. Praktiskt område: 8–18 °C. Över ~18 °C kan värmepumpen stänga av sig helt.

-----

### Ramptiming

```python
RAMP_SCALE: Final[float] = 10.0         # multiplikator i rampformeln
RAMP_MIN_MINUTES: Final[float] = 20.0   # golv — aldrig kortare än detta
RAMP_MAX_MINUTES: Final[float] = 60.0   # tak — aldrig längre än detta
```

Styr hur lång tid bromsen tar att rampa in och ut. Den faktiska ramptiden beräknas från **Bromsramptid**-slidern:

```
ramp_in = clamp(slider × RAMP_SCALE, RAMP_MIN, RAMP_MAX)
```

Höj `RAMP_SCALE` för att ge slidern mer utslag utan att behöva höga slidervärden. Höj `RAMP_MAX_MINUTES` om du har ett mycket tungt hus och vill ha ännu mjukare övergångar.

-----

### Förvärmning

```python
PREHEAT_BOOST_C: Final[float] = 4.0
```

Extra värmebehov som läggs ovanpå PI-utsignalen under förvärmningsfönstret (innan en dyr period, när det är kallt). Sänker den falska utomhustemperaturen något mer (mer värme) för att bygga upp termisk massa. Aktiv bara när `preheat_boost_enabled` är True (standard).

-----

### Toppfilter

```python
PEAK_FILTER_MIN_DURATION_MINUTES: Final[int] = 30
```

Dyra pristoppar kortare än detta ignoreras. Förhindrar att bromsen aktiveras för ett enskilt 15-minutersslot omgivet av billiga slots.

-----

### Prisframförhållning

```python
PRICE_LOOKAHEAD_HOURS: Final[int] = 6
```

Hur många timmar framåt PumpSteer scannar efter kommande dyra perioder när den avgör om förvärmning eller förbromskromsning ska starta.

-----

### Bromshålltid

```python
BRAKE_HOLD_MINUTES: Final[float] = 30.0
```

Efter att priset sjunker från dyrt till normalt hålls bromsen aktiv i så här många minuter innan den släpper. Förhindrar snabb på/av-cykling när det finns en kort billig dipp mitt i ett dyrt block.

-----

### Förvärmning vid saknad prognos

```python
PREHEAT_ON_MISSING_FORECAST: Final[bool] = False
```

Vad som händer när väderentiteten saknar prognosdata. `False` (standard) = ingen förvärmning triggas. `True` = saknad prognos behandlas som kallt väder och förvärmning tillåts. Rekommenderas att lämna på `False` om inte din väderentitet ofta är otillgänglig och du befinner dig i ett kallt klimat.

-----

### Semestertemperatur

```python
HOLIDAY_TEMP: Final[float] = 16.0
```

Måltemperaturen som används när semesterläge är aktivt.
