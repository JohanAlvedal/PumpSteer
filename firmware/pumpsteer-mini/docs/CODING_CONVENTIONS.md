# Coding conventions

- Language: C++ for firmware/core, CMake for builds.
- Code comments must be written in English.
- Prefer fixed-size storage or bounded containers in long-lived embedded paths where practical.
- Keep hardware dependencies out of `pumpsteer_core` and `thermal_learning` where possible.
- Validate all external numeric values before use.
- Express units in names when ambiguity is possible (`_c`, `_ms`, `_hours`, `_percent`).
- Avoid hidden singleton state in the hardware-independent control logic.
- Add host tests for new hardware-independent behavior.
