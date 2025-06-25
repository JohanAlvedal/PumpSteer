# 🌡️ PumpSteer Home Assistant Integration

<img src="https://github.com/JohanAlvedal/PumpSteer/blob/main/icons/icon.png" alt="PumpSteer Logo" width="120" /> 

## English – Overview

PumpSteer is a custom Home Assistant integration that creates a dynamic, virtual outdoor temperature sensor. This sensor helps intelligently control your heat pump or boiler by adjusting the reported outdoor temperature based on indoor temperature, electricity price, weather forecast, and thermal inertia.

### Features

* Adaptive temperature control
* Optional pre-boost heating
* Summer mode override
* Aggressiveness control
* Learns your home's thermal inertia
* Fully local – no cloud dependency

### Required Entities

* `sensor.indoor_temperature`
* `sensor.real_outdoor_temperature`
* `sensor.electricity_price_forecast`
* `input_number.indoor_target_temperature`
* `input_number.pumpsteer_summer_threshold`

### Optional Entities

* `input_number.pumpsteer_aggressiveness`
* `input_number.house_inertia`
* `input_text.hourly_forecast_temperatures`

### Output Sensor: `sensor.virtual_outdoor_temp`

This virtual sensor reports a modified outdoor temperature. It also exposes attributes:

| Attribute              | Description                                                           |
| ---------------------- | --------------------------------------------------------------------- |
| `indoor_temperature`   | Current indoor temperature (`sensor.indoor_temperature`)              |
| `target_temperature`   | Desired target temperature (`input_number.indoor_target_temperature`) |
| `electricity_price`    | Current electricity price                                             |
| `outdoor_real`         | Real outdoor temperature (`sensor.real_outdoor_temperature`)          |
| `summer_threshold`     | Threshold for activating summer mode                                  |
| `thermal_inertia`      | Calculated or user-defined inertia                                    |
| `delta_to_target`      | Difference between indoor and target temperature                      |
| `aggressiveness`       | Responsiveness of the system                                          |
| `scaling_factor`       | Internal multiplier used in calculations                              |
| `mode`                 | Current mode (`heating`, `pre_boost`, `summer_mode`, etc.)            |
| `virtual_outdoor_temp` | Same as main sensor state (included as attribute)                     |

### Installation Guide

**Note:** All required `input_number` and `input_text` helpers are already included in the default `packages` file provided with this integration. You only need to set up an automation to regularly populate `input_text.hourly_forecast_temperatures` if you plan to use the pre-boost feature.

#### Example automation to fill hourly forecast (if using pre-boost)

```yaml
alias: Update hourly forecast for PumpSteer
mode: single
trigger:
  - platform: time_pattern
    minutes: "5"
action:
  - service: input_text.set_value
    target:
      entity_id: input_text.hourly_forecast_temperatures
    data:
      value: >
        {% set forecast = state_attr('weather.smhi', 'forecast') %}
        {% if forecast is none %}unavailable{% else %}
        {% set temps = forecast[:6] | map(attribute='temperature') | list %}
        {{ temps | join(',') }}
        {% endif %}
```

**Note:** All required `input_number` and `input_text` helpers are already included in the default `packages` file provided with this integration. You only need to set up an automation to regularly populate `input_text.hourly_forecast_temperatures` if you plan to use the pre-boost feature.

1. **Download or clone this repository.**
2. Copy the folder `pumpsteer` into your Home Assistant custom components directory:

   ```
   <config>/custom_components/pumpsteer/
   ```
3. Make sure your `configuration.yaml` is properly set up for any needed `input_number`, `input_text`, and sensors.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Integrations**.
6. Click **"Add Integration"**, then search for **PumpSteer** and follow the setup wizard.
7. Done! You should now have a sensor called `sensor.virtual_outdoor_temp`.

---

## 🇸🇪 Svenska – Översikt

PumpSteer är en Home Assistant-integration som skapar en dynamisk, virtuell utomhustemperatursensor. Denna sensor ger smart styrning av din värmepump eller panna genom att justera rapporterad utetemperatur baserat på innetemperatur, elpris, väderprognos och husets värmetröghet.

### Funktioner

* Adaptiv temperaturstyrning
* Möjlighet till förvärmning ("pre-boost")
* Sommarläge stänger av uppvärmning vid varmt väder
* Justerbar aggressivitet i styrningen
* Lär sig husets värmetröghet
* Helt lokal – ingen molntjänst krävs

### Kräver följande entiteter

* `sensor.indoor_temperature`
* `sensor.real_outdoor_temperature`
* `sensor.electricity_price_forecast`
* `input_number.indoor_target_temperature`
* `input_number.pumpsteer_summer_threshold`

### Valbara entiteter

* `input_number.pumpsteer_aggressiveness`
* `input_number.house_inertia`
* `input_text.hourly_forecast_temperatures`

### Utdatavärde: `sensor.virtual_outdoor_temp`

Denna sensor rapporterar en manipulerad utomhustemperatur. Den visar också följande attribut (på engelska):

| Attribute              | Beskrivning                             |
| ---------------------- | --------------------------------------- |
| `indoor_temperature`   | Aktuell temperatur inomhus              |
| `target_temperature`   | Önskad temperatur inomhus               |
| `electricity_price`    | Aktuellt elpris                         |
| `outdoor_real`         | Verklig utomhustemperatur               |
| `summer_threshold`     | Gräns för att aktivera sommarläge       |
| `thermal_inertia`      | Beräknad eller manuell värmetröghet     |
| `delta_to_target`      | Skillnad mellan inne- och måltemperatur |
| `aggressiveness`       | Hur känslig styrningen är               |
| `scaling_factor`       | Intern beräkningsfaktor                 |
| `mode`                 | Aktuellt driftläge                      |
| `virtual_outdoor_temp` | Sensorvärdet även som attribut          |

### Installationsguide

**Obs!** Alla nödvändiga `input_number` och `input_text` är redan inkluderade i den medföljande `packages`-filen. Det enda du själv behöver skapa är en automation som uppdaterar `input_text.hourly_forecast_temperatures` om du vill använda pre-boost-funktionen.

#### Exempelautomation för att fylla väderprognosen (vid pre-boost)

```yaml
alias: Uppdatera timvis prognos till PumpSteer
mode: single
trigger:
  - platform: time_pattern
    minutes: "5"
action:
  - service: input_text.set_value
    target:
      entity_id: input_text.hourly_forecast_temperatures
    data:
      value: >
        {% set forecast = state_attr('weather.smhi', 'forecast') %}
        {% if forecast is none %}unavailable{% else %}
        {% set temps = forecast[:6] | map(attribute='temperature') | list %}
        {{ temps | join(',') }}
        {% endif %}
```

**Obs!** Alla nödvändiga `input_number` och `input_text` är redan inkluderade i den medföljande `packages`-filen. Det enda du själv behöver skapa är en automation som uppdaterar `input_text.hourly_forecast_temperatures` om du vill använda pre-boost-funktionen.

1. **Ladda ner eller klona detta GitHub-repo.**
2. Kopiera mappen `pumpsteer` till din Home Assistant-mapp för anpassade komponenter:

   ```
   <config>/custom_components/pumpsteer/
   ```
3. Säkerställ att `configuration.yaml` innehåller rätt `input_number`, `input_text` och sensorer.
4. Starta om Home Assistant.
5. Gå till **Inställningar → Enheter & Tjänster → Integrationer**.
6. Klicka på **"Lägg till integration"**, sök efter **PumpSteer** och följ guiden.
7. Klart! Nu finns sensorn `sensor.virtual_outdoor_temp` tillgänglig.

För avancerade exempel, automations, visualiseringar och förslag på Lovelacekort, se projektets GitHub-sida.
