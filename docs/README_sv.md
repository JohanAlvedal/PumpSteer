# 🔥 PumpSteer 2.X – Smart Värmepumpsoptimering

➡️ English version: [README (English)](README.md)

> ⚠️ **Stor uppdatering.** Vänligen läs [Installations- och uppgraderingsguiden](docs/INSTALLATION.md) före installation.

PumpSteer är en anpassad integration för Home Assistant som optimerar din värmepump genom att dynamiskt justera den **virtuella utomhustemperaturen**.

Den sänker dina energikostnader under dyra eltimmar samtidigt som inomhuskomforten bibehålls med hjälp av intelligent PI-reglering.

<a href="https://www.buymeacoffee.com/alvjo" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px !important;width: 200px !important;">
</a>

---

## 📸 Förhandsvisning av Dashboard

<table>
  <tr>
    <td><img src="docs/img/01.png" width="200"/></td>
    <td><img src="docs/img/02.png" width="200"/></td>
    <td><img src="docs/img/03.png" width="200"/></td>
  </tr>
</table>

---

## 📘 Dokumentation

För att hålla ordning på allt är dokumentationen uppdelad i följande avsnitt:

### 🚀 Kom igång
* **[Installationsguide](docs/INSTALLATION.md)** – Steg-för-steg setup och anteckningar för uppgradering från v1.6.6.
* **[Konfiguration](docs/Configuration_sv.md)** – Detaljerad genomgång av integrationens inställningar (på svenska).
* **[Dashboard-inställningar](docs/DASHBOARD.md)** – Hur du använder de medföljande Lovelace-mallarna.

### 🧠 Djupdykning
* **[Systemarkitektur](docs/ARCHITECTURE.md)** – Så fungerar PI-regleringen och tillståndsmaskinen (state machine).
* **[Trimningsguide](docs/TUNING.md)** – Optimera tröghet (Inertia) och aggressivitet för just ditt hem.
* **[Beslut & Logik](docs/DECISIONS.md)** – Resonemanget bakom de valda kontrollstrategierna.

### 🛠 Support & Framtid
* **[Felsökning](docs/TROUBLESHOOTING.md)** – Vanliga problem och hur du löser dem.
* **[Ändringslogg](docs/CHANGELOG.md)** – Versionshistorik och uppdateringar.
* **[Roadmap](docs/ROADMAP.md)** – Planerade funktioner och framtida utveckling.

---

## 🔧 Hur det fungerar (Kortversionen)

PumpSteer beräknar en **virtuell utomhustemperatur** baserat på elpriser, inomhustemperatur och väderprognoser.

Värdet skickas till hårdvara (som en **Ohmigo**-enhet) som är ansluten till värmepumpens utomhusgivare. Värmepumpen "ser" då en annan temperatur och justerar sin drift därefter – vilket sparar pengar utan att behöva krångla med komplexa Modbus-inställningar eller moln-API:er.

---

## ⚠️ Ansvarsfriskrivning

Användning av denna integration sker på egen risk. Uppvärmning är ett kritiskt system i ditt hem. Felaktiga inställningar kan leda till bristande komfort eller potentiella skador. Övervaka alltid systemets beteende noggrant efter installation.

---

## 🔗 Länkar
- 🐞 [Rapportera fel / Önska funktioner](https://github.com/JohanAlvedal/PumpSteer/issues)
- 📝 Licens: AGPL-3.0
- © Johan Älvedal
