# 🌡️ VirtualOutdoorTemp

Simulate a virtual outdoor temperature to steer your heat pump or boiler intelligently based on:

- Indoor temperature
- Electricity price
- Weather forecast (optional)
- House thermal inertia

---

## ⚙️ Features

- Adaptive temperature steering
- **Optional Pre-boost:** Proactively heats your home when cold temperatures are expected and electricity prices are high. Requires both electricity price and weather forecast to be configured.
- Summer mode override
- Aggressiveness control
- Learns how your home retains heat
- Works entirely locally

---

## 📌 Förutsättningar

* Home Assistant 2023.12 eller nyare.
* Sensorer tillgängliga i Home Assistant för:
    * Aktuell inomhustemperatur.
    * Aktuell verklig utomhustemperatur.
    * Elprisprognoser (en sensor som exponerar framtida priser i attributet `today`, t.ex. från Nordpool eller Tibber integrationer).
    * Önskad måltemperatur (en `input_number` entitet).
    * Sommarlägeströskel (en `input_number` entitet).
    * (Valfritt) Husets termiska tröghet (en `input_number` entitet, t.ex. `input_number.house_inertia`). Om denna inte finns, använder integrationen ett beräknat värde.
    * (Valfritt, rekommenderas) Aggressivitetskontroll (en `input_number` entitet, t.ex. `input_number.virtualoutdoortemp_aggressiveness`). Om denna inte finns, används ett standardvärde (1.0).

### För Pre-boost (valfritt)

För att aktivera pre-boost-funktionen måste du även tillhandahålla:

* **Väderprognostemperaturer** (en `input_text` entitet). Denna `input_text` måste *själv* uppdateras regelbundet, t.ex. via en Home Assistant-automatisering. Den ska innehålla en kommaseparerad sträng av framtida timvisa temperaturer (t.ex. `"2.5,3.1,4.0,..."`).

    **Exempel på automatisering för `input_text.hourly_forecast_temperatures`:**
    (Anpassa `weather.your_weather_integration` till din faktiska väderentitet och dess attribut.)

    ```yaml
    alias: Uppdatera väderprognos för VirtualOutdoorTemp Pre-boost
    description: Fyller input_text med kommaseparerade temperaturprognoser för VirtualOutdoorTemp.
    trigger:
      - platform: time_pattern
        minutes: "5" # Kör varje timme vid xx:05
    condition: []
    action:
      - service: input_text.set_value
        target:
          entity_id: input_text.hourly_forecast_temperatures # Välj denna entitet i VirtualOutdoorTemp-konfigurationen
        data_template:
          value: >
            {% set forecast = state_attr('weather.smhi', 'forecast') %} {# Exempel med SMHI, anpassa till din #}
            {% set temps = [] %}
            {# Plocka ut de första 6 timmarnas temperaturer, anpassa lookahead_hours i pre_boost.py vid behov #}
            {% for item in forecast | list | selectattr('temperature', 'is_number') | list %}
              {% if loop.index <= 6 %}
                {% set temps = temps + [item.temperature] %}
              {% endif %}
            {% endfor %}
            {{ temps | join(',') }}
    mode: single
    ```

---
