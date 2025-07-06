# PumpSteer

PumpSteer är en anpassad Home Assistant-integration för att dynamiskt optimera din värmepump genom att manipulera insignalen från utomhustemperatursensorn. Den låter dig spara energi och pengar genom att anpassa din uppvärmningsstrategi baserat på elpriser, inomhustemperatur och väderprognoser.

-----

# Ansvarsfriskrivning

Jag är inte expert på programmering, energihantering eller automation. Denna setup är baserad på mina personliga erfarenheter och experiment. Jag kan inte garantera att den fungerar för alla, och jag tar inget ansvar för problem eller skador som kan uppstå vid användning av denna konfiguration eller kod.
Använd den på egen risk och testa noggrant i din egen miljö.

## ✅ Funktioner

- 🔧 **Smart virtuell styrning av utomhustemperatur**
- ⚡ Anpassar uppvärmningsstrategin baserat på:  
  - Inomhustemperatur  
  - Måltemperatur  
  - Prognos för elpris  
  - Temperaturprognos
- 🌡️ Fejkat utomhustemperatur beräknas för att lura värmepumpen att spara eller buffra energi
- 🚀 **Pre-boost-läge:** bygg upp en värmebuffert före kalla och dyra pristoppar
- 🧊 **Bromsläge:** undvik uppvärmning under de dyraste timmarna
- 🏖️ **Sommarläge:** inaktiverar fejkad temperatur när utomhustemperaturen är över tröskelvärdet
- 🏝️ **Semesterläge:** När semesterläget är aktiverat och aktuell tid ligger inom de valda datumen, sänks inomhustemperaturen till 16 grader tills du är tillbaka.
- 📦 **Enkel installation** med medföljande `packages`-fil för hjälpentiteter
- 📊 Helt lokalt (inga molnberoenden)
- 🧠 Självjusterande beräkning av husets tröghet
- 🔄 Stöder komfortprofiler via en aggressivitetsinställning
- 📈 ApexCharts-exempel ingår för visualisering


> **Obs\!**
> Semesterläge är endast aktivt när sommarläge *inte* är aktivt.
> Om utomhustemperaturen är över sommar-tröskeln kommer sommarläget alltid att prioriteras över semesterläget.
> Detta innebär att uppvärmningen minimeras under varma perioder, även om semesterläget är aktiverat.

-----

## Lägg till PumpSteer till HACS som ett anpassat arkiv (Custom Repository)

Om PumpSteer ännu inte finns tillgängligt i HACS standardbutik kan du lägga till det manuellt som ett anpassat arkiv:

I Home Assistant, gå till HACS i sidofältet.
Klicka på menyn med tre punkter (⋮) i det övre högra hörnet och välj "Custom repositories" (Anpassade arkiv).
I fältet "Repository" (Arkiv), ange:

```

[https://github.com/JohanAlvedal/PumpSteer](https://github.com/JohanAlvedal/PumpSteer)

````

Ställ in kategorin till "Integration".
Klicka på "Add" (Lägg till).
PumpSteer kommer nu att visas under HACS \> Integrations. Klicka på "Install" för att lägga till det.
Starta om Home Assistant efter installationen.
Fortsätt med konfigurationsstegen som beskrivits ovan.
Obs:
Så länge PumpSteer inte finns i den officiella HACS-butiken måste du upprepa dessa steg om du installerar om HACS eller rensar dess konfiguration.

-----

## 🔧 Installation och Konfiguration

Följ dessa tre steg för att få PumpSteer igång.

### Steg 1: Skapa hjälpentiteter (via Packages)

För att göra setup så enkel som möjligt, innehåller detta projekt en paketfil som skapar alla nödvändiga `input_number`- och `input_text`-hjälpare åt dig.

1.  **Ladda ner filen `pumpsteer_package.yaml`** från arkivet.

2.  Placera filen i din `/config/packages/` katalog. Om `packages`-katalogen inte finns i roten av din `/config`-mapp, måste du skapa den.

3.  **Aktivera packages** i din huvudsakliga `configuration.yaml`-fil. Om du inte redan har gjort det, lägg till följande rader. Om du redan har en `homeassistant:`-sektion, lägg bara till `packages:`-raden till den.

    ```yaml
    homeassistant:
      packages: !include_dir_named packages
    ```

4.  **Starta om Home Assistant.** Efter omstart kommer alla nödvändiga hjälpare (listade i avsnittet "Referens för hjälpentiteter" nedan) att vara tillgängliga.

### Steg 2: Installera den anpassade komponenten

Detta är standardproceduren för att installera en anpassad komponent.

1.  Placera katalogen `pumpsteer` (som innehåller `sensor.py`, `pre_boost.py`, etc.) i din Home Assistant-mapp `custom_components`.
2.  Starta om Home Assistant igen.

### Steg 3: Lägg till integrationen

1.  Navigera till **Inställningar \> Enheter och Tjänster \> Lägg till Integration**.
2.  Sök efter och välj **PumpSteer**.
3.  I konfigurationsdialogen, välj de hjälpentiteter som skapades av paketfilen.

-----

## 📄 Referens för hjälpentiteter

Genom att använda den medföljande filen `pumpsteer_package.yaml` kommer följande entiteter att skapas. Du kan justera deras värden från Home Assistant-gränssnittet under **Inställningar \> Enheter och Tjänster \> Hjälpare**.

| Typ | Beskrivning |
| :--- | :--- |
| `sensor` | Inomhustemperaturgivare (måste du tillhandahålla) |
| `sensor` | Verklig utomhustemperaturgivare (måste du tillhandahålla) |
| `sensor` | Elprissensor (måste du tillhandahålla, t.ex. Nordpool eller Tibber) |
| `input_text` | Lagrar de timvisa prognostiserade temperaturerna (CSV-sträng, 24 värden) |
| `input_number`| Din önskade målinomhustemperatur |
| `input_number`| Utomhustemperaturtröskeln för att aktivera sommarläge |
| `input_number` | Aggressivitetsnivån för besparingar vs. komfort (0,0 till 5,0) |
| `input_number` | Den beräknade husets tröghet (du kan låta PumpSteer hantera detta eller åsidosätta det) |

-----

## 🧪 Prognosformat

`input_text`-entiteten för temperaturprognosen måste innehålla **högst 24 kommaseparerade värden** som representerar de timvisa prognostiserade utomhustemperaturerna för de kommande 24 timmarna:

```text
-3.5,-4.2,-5.0,-4.8,... (totalt 24 värden)
````

Om strängen är ogiltig eller ofullständig, kommer sensorn att logga en varning och tillfälligt avbryta beräkningarna tills giltig data är tillgänglig.

-----

## 📊 Sensorutgångar

PumpSteer skapar två sensorer.

### 1\. `sensor.pumpsteer` (Kontrollsensor)

Denna sensor tillhandahåller den beräknade virtuella temperaturen.

**Tillstånd:** Den fejkade utomhustemperaturen (`°C`) som ska skickas till din värmepump.

**Attribut:**

| Attribut | Betydelse |
| :--- | :--- |
| `Läge` | Aktuellt driftläge. Kan vara: `heating`, `neutral`, `braking_by_temp`, `summer_mode`, `preboost`, `braking_mode` |
| `Ute (verklig)` | Aktuell temperatur från den verkliga utomhussensorn |
| `Inne (mål)` | Din önskade inomhustemperatur |
| `Inne (verklig)` | Aktuell inomhustemperatur |
| `Inertia` | Hur långsamt huset reagerar på förändringar i utomhustemperaturen (högre = bättre isolerat) |
| `Aggressiveness` | Från 0,0 (passiv) till 5,0 (aggressiv besparing) |
| `Summer threshold` | Utomhustemperaturtröskeln för att inaktivera värmekontroll |
| `Elpriser (prognos)` | Timvisa elpriser från din prissensor |
| `Pre-boost Aktiv` | Sant om pre-boost eller bromsning är aktiv (pausar tröghetsberäkningen) |

### 2\. `sensor.pumpsteer_future_strategy` (Diagnossensor)

Denna sensor ger insikter om *varför* systemet fattar sina beslut.

**Tillstånd:**
Antalet kommande timmar som identifierats som både kalla och dyra.

**Attribut:**

| Attribut | Betydelse |
| :--- | :--- |
| `preboost_expected_in_hours` | Hur många timmar i förväg systemet kommer att starta pre-boost, baserat på husets tröghet. |
| `first_preboost_hour` | Klockslaget (t.ex. "18:00") för nästa förväntade pre-boost-händelse. |
| `cold_and_expensive_hours_next_6h` | Totalt antal timmar identifierade som "kalla & dyra" under de närmaste 6 timmarna. |
| `expensive_hours_next_6h` | Totalt antal timmar som anses "dyra" under de närmaste 6 timmarna. |
| `braking_price_threshold_percent` | Aktuell priströskel (i % av maxpris) för att aktivera bromsläge. |

-----

## Aggressivitet – Vad gör den?

Aggressivitet (0,0 till 5,0) styr avvägningen mellan energibesparingar och inomhuskomfort. Den påverkar både när uppvärmningen minskas (bromsning) och när extra uppvärmning läggs till (pre-boost).

| Inställning | Bromsbeteende | Pre-boost-beteende |
| :--- | :--- | :--- |
| **Låg** (t.ex. 0-1) | Bromsar sällan, endast vid de absolut högsta priserna. | Ökar lättare för att prioritera komfort. |
| **Hög** (t.ex. 4-5) | Bromsar tidigt och ofta, även vid måttliga pristoppar. | Ökar endast i de mest nödvändiga fallen för att spara energi. |

**Högre aggressivitet sparar mer pengar, men kan minska inomhuskomforten.**

-----

## 📈 ApexCharts Exempel

### Visualisera temperaturer

```yaml
type: custom:apexcharts-card
header:
  title: PumpSteer Temperaturkontroll
graph_span: 24h
span:
  start: day
series:
  - entity: sensor.pumpsteer
    name: Fejkad utomhustemp
  - entity: sensor.ute_verklig_temp
    name: Real Outdoor Temp
  - entity: sensor.inne_verklig_temp
    name: Inomhustemp
  - entity: input_number.varmepump_target_temp
    name: Måltemp
    stroke_width: 2
    curve: stepline
```

### Visualisera framtida strategi

```yaml
type: custom:apexcharts-card
header:
  title: PumpSteer - Framtida hot
chart_type: bar
graph_span: 24h
series:
  - entity: sensor.pumpsteer_future_strategy
    name: Kalla & dyra timmar
    attribute: cold_and_expensive_hours_next_6h
  - entity: sensor.pumpsteer_future_strategy
    name: Expensive Hours
    attribute: expensive_hours_next_6h
```

-----

## 🧠 Hur det fungerar

PumpSteer beräknar en "fejkad" utomhustemperatur för att knuffa din värmepump till att antingen:

  - **Pre-boosta:** Värma mer när priser och temperaturer är låga, före en kommande kall och dyr pristopp.
  - **Bromsa:** Undvika uppvärmning när priserna är som högst.
  - **Normalt:** Justera försiktigt uppvärmningen för att bibehålla komfort med minimal kostnad.
  - **Sommarläge:** Stå ner när det är varmt ute.

-----

## 💬 Loggning och Felsökning

  - Varningar och fel loggas i standardloggen för Home Assistant.
  - Om nödvändig sensordata inte är tillgänglig, kommer PumpSteer att visa `unavailable` och försöka igen automatiskt.
  - Husets tröghetsvärde beräknas och uppdateras automatiskt om du inte anger en manuell åsidosättning via ett `input_number`.

-----

## En notering från utvecklaren

Denna integration har byggts av en amatörutvecklare med kraftfull assistans av Googles Gemini och Copilot. Det är resultatet av en passion för smarta hem, mycket trial and error, och många, många Home Assistant restarts.

Vänligen betrakta detta som en **betaprodukt** i ordets sannaste bemärkelse.

Om du är kunnig inom detta område välkomnas konstruktiv feedback, förslag och bidrag varmt. Var tålmodig, då detta är ett lärande projekt.

-----

## 🔗 Länkar

  - [Ärendehanterare](https://github.com/JohanAlvedal/pumpsteer/issues)

-----

## 📄 Licens

© Johan Älvedal
