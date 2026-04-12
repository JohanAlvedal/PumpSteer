# Changelog

## [2.1.0]

### Added
- Thermal Outlook sensor
- Preheat boost switch

### Changed
- Refactored forecast and thermal model

### Notes
- Diagnostic features only (no control changes)

---

## 2.0.0 (The Big Rewrite)
- **New Control System:** Replaced heuristics with PI-based control.
- **Price Classification:** Simplified to `cheap / normal / expensive`.
- **State Machine:** Predictable behavior and status reporting.
- **Dynamic Braking:** Added ramping, hold logic, and peak filtering.
- **Managed Entities:** Integration now owns numbers, switches, and datetime entities.
- **Local First:** No cloud dependencies.
