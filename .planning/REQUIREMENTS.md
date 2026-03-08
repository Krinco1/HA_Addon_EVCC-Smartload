# Requirements: SmartLoad v1.2

**Defined:** 2026-03-08
**Core Value:** Das System trifft zu jedem Zeitpunkt die wirtschaftlich beste Energieentscheidung -- und der Nutzer versteht warum.

## v1.2 Requirements

### PV Forecast

- [x] **PVFC-01**: PV-Prognose stimmt mit evcc-Werten überein (kein ~2x Faktor)

### evcc Integration

- [x] **EVCC-01**: SmartLoad-Interventionen (Battery Locking) stören evcc PV-Surplus-Modus nicht
- [x] **EVCC-02**: SmartLoad greift nur ein wenn nötig, respektiert evcc-native PV-Steuerung

### Vehicle Data

- [x] **VHCL-01**: Vehicle Polling holt zuverlässig SoC-Daten von API-Providern
- [x] **VHCL-02**: Wallbox-verbundene Fahrzeuge zeigen korrekten Stale-Status (evcc-Websocket-Updates berücksichtigt)

### Charge Sequencer

- [x] **CHRG-01**: Nächstes Fahrzeug in Multi-Vehicle-Queue startet sofort nach Abschluss des vorherigen (kein 15-Min-Delay)

### Data Integrity

- [x] **DATA-01**: ManualSoC-Override geht nicht verloren bei gleichzeitigem API-Poll

## v2.0 Requirements

### Dashboard Redesign

- **DASH-01**: Dashboard Design an evcc Web-UI angleichen (Farben, Schriften, Layout)
- **DASH-02**: evcc Web-UI als iframe-Tab einbetten (optional per Schalter)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Settings UI (SLF-002) | Feature, nicht Bugfix -- v2.0+ |
| Live Log View (SLF-003) | Feature -- v2.0+ |
| API Authentication (SLF-008) | Feature -- v2.0+ |
| Health Check erweitern (SLF-007) | Feature -- v2.0+ |
| PV Forecast vs Actual Monitoring (SLF-001) | Feature -- PVFC-01 fixt den Bug, Monitoring ist v2.0+ |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PVFC-01 | Phase 13 | Complete |
| EVCC-01 | Phase 13 | Complete |
| EVCC-02 | Phase 16 (gap closure) | Complete |
| VHCL-01 | Phase 14 | Complete |
| VHCL-02 | Phase 14 | Complete |
| DATA-01 | Phase 14 | Complete |
| CHRG-01 | Phase 15 | Complete |

**Coverage:**
- v1.2 requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0

---
*Requirements defined: 2026-03-08*
*Last updated: 2026-03-08 after gap closure planning*
