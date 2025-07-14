# PumpSteer

PumpSteer är en anpassad Home Assistant-integration för att dynamiskt optimera din värmepump genom att manipulera insignalen från utomhustemperatursensorn. Den låter dig spara energi och pengar genom att anpassa din uppvärmningsstrategi baserat på elpriser, inomhustemperatur, väderprognoser och termisk tröghet.

-----

# Ansvarsfriskrivning

Jag är inte expert på programmering, energihantering eller automation. Denna setup är baserad på mina personliga erfarenheter och experiment. Jag kan inte garantera att den fungerar för alla, och jag tar inget ansvar för problem eller skador som kan uppstå vid användning av denna konfiguration eller kod.

**Använd den på egen risk och testa noggrant i din egen miljö.**
=======
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


> **Obs\!**
> Semesterläge är endast aktivt när sommarläge *inte* är aktivt.
> Om utomhustemperaturen är över sommar-tröskeln kommer sommarläget alltid att prioriteras över semesterläget.
> Detta innebär att uppvärmningen minimeras under varma perioder, även om semesterläget är aktiverat.
> 
=======
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
| `Pre-boost Aktiv` | Sant om pre-boost eller bromsning är aktiv (pausar tröghetsberäkningen) |

-----

## Aggressivitet – Vad gör den?

Aggressivitet (0,0 till 5,0) styr avvägningen mellan energibesparingar och inomhuskomfort. Den påverkar både när uppvärmningen minskas (bromsning) och när extra uppvärmning läggs till (pre-boost).

| Inställning | Bromsbeteende | Pre-boost-beteende |
| :--- | :--- | :--- |
| **Låg** (t.ex. 0-1) | Bromsar sällan, endast vid de absolut högsta priserna. | Ökar lättare för att prioritera komfort. |
| **Hög** (t.ex. 4-5) | Bromsar tidigt och ofta, även vid måttliga pristoppar. | Ökar endast i de mest nödvändiga fallen för att spara energi. |

**Högre aggressivitet sparar mer pengar, men kan minska inomhuskomforten.**

-----

## 🧠 Hur det fungerar

PumpSteer beräknar en "fejkad" utomhustemperatur för att knuffa din värmepump till att antingen:

  - **Pre-boosta:** Värma mer när priser och temperaturer är låga, före en kommande kall och dyr pristopp.
  - **Bromsa:** Undvika uppvärmning när priserna är som högst.
  - **Normalt:** Justera försiktigt uppvärmningen för att bibehålla komfort med minimal kostnad.
  - **Sommarläge:** Stå ner när det är varmt ute

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

© Johan Ä
