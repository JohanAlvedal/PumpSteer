# PumpSteer

<p align="center">
  <a href="https://github.com/Johan-Alvedal/PumpSteer/issues">
    <img src="https://img.shields.io/github/issues/Johan-Alvedal/PumpSteer" alt="Issues" />
  </a>
  <a href="https://github.com/Johan-Alvedal/PumpSteer/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/Johan-Alvedal/PumpSteer" alt="License" />
  </a>
</p>

PumpSteer är en anpassad Home Assistant-integration för att dynamiskt optimera din värmepump genom att manipulera insignalen från utomhustemperatursensorn. Den låter dig spara energi och pengar genom att anpassa din uppvärmningsstrategi baserat på elpriser, inomhustemperatur och väderprognoser.

### ✅ Funktioner

* **Smart virtuell utomhustemperaturkontroll**
* **Anpassar uppvärmningsstrategin baserat på:**
    * Inomhustemperatur
    * Måltemperatur
    * Elprisprognos
    * Temperaturprognos
* **"Fejkad" utomhustemperatur** beräknas för att lura värmepumpen att spara eller buffra energi.
* **🚀 Pre-boost-läge**: Bygg upp en värmebuffert före kalla och dyra pristoppar.
* **🧊 Bromsläge**: Undvik uppvärmning under de dyraste timmarna.
* **🏖️ Sommar-läge**: Inaktiverar "fejkad" temperatur när utomhustemperaturen överstiger ett visst tröskelvärde.
* **📦 Enkel installation** med en medföljande paketfil för hjälpentiteter.
* **📊 Helt lokal** (inga molnberoenden).
* **🧠 Självjusterande beräkning av husets tröghet (inertia)**.
* **🔄 Stöder komfortprofiler** via en aggressivitetsinställning.
* **📈 ApexCharts-exempel** för visualisering ingår.

---

### 🔧 Installation och konfiguration

Följ dessa tre steg för att få PumpSteer igång.

#### Steg 1: Skapa hjälpentiteter (via paket)

För att göra installationen så enkel som möjligt, innehåller detta projekt en paketfil som skapar alla nödvändiga `input_number` och `input_text` hjälpare åt dig.

1.  Ladda ner filen [`pumpsteer_package.yaml`](pumpsteer_package.yaml) från detta repository.
2.  Placera denna fil i din `/config/packages/`-katalog. Om `packages`-katalogen inte finns i roten av din `/config`-mapp måste du skapa den.
3.  Aktivera paket i din huvudsakliga `configuration.yaml`-fil. Om du inte redan har gjort det, lägg till följande rader. Om du redan har en `homeassistant:`-sektion, lägg bara till raden `packages:` till den.

```yaml
homeassistant:
  packages: !include_dir_named packages
