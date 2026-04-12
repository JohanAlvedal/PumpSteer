# 🔧 Tuning & Performance

### Aggressiveness Level
Controls how hard the system reacts to price changes.
- **0:** No price control.
- **1–2:** Mild response.
- **3–4:** Balanced (Recommended for most).
- **5:** Aggressive price chasing.

### Inertia
Matches the thermal mass of your building.
- **Low:** For apartments or light wooden houses (fast response).
- **Medium:** For standard detached houses.
- **High:** For heavy stone/concrete houses with high thermal mass.

### Recorder Requirement
The system requires at least **72 hours of price history** in the Home Assistant Recorder to function correctly. If missing, "Safe Mode" may trigger.
