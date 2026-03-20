# evcc Vehicle Polling — Validierungsbericht

**Datum:** 2026-03-20
**evcc Version:** 0.303.1
**Ergebnis:** NO-GO fuer Vehicle Polling Migration

## Testparameter

- evcc `/api/state` manuell abgerufen
- 3 Fahrzeuge konfiguriert: KIA_EV9, my_Twingo (Renault), ORA_03 (offline)
- 1 Loadpoint (Kostal Enector)
- KIA_EV9 zum Testzeitpunkt angesteckt und ladend (PV-Modus)

## Ergebnisse

### API-State Analyse

```
vehicles[]:
  KIA_EV9:   soc=null
  my_Twingo: soc=null
  ora_03:    soc=null

loadpoints[0]:
  vehicleName=KIA_EV9
  vehicleSoc=25.807
  connected=true, charging=true
```

### Zentrale Erkenntnis

**`poll.mode: always` ist ein Loadpoint-Setting, kein Vehicle-Setting.**

Unsere Dokumentation (`docs/evcc-loadpoint-setup.md`) zeigte `poll.mode` falsch unter
`vehicles:` — das wird von evcc ignoriert. Der korrekte Ort ist:

```yaml
loadpoints:
  - soc:
      poll:
        mode: always
        interval: 60m
```

### Architektur-Limitation

| Fakt | Auswirkung |
|------|------------|
| `vehicles[].soc` liefert immer `null` | SoC nur ueber `loadpoints[].vehicleSoc` verfuegbar |
| `poll.mode: always` pollt nur das zugewiesene Fahrzeug | Bei 3 EVs auf 1 LP: nur 1 bekommt SoC |
| Fahrzeugwechsel nur ueber UI oder API | SmartLoad muesste Fahrzeuge rotieren |

**Konsequenz:** evcc kann nicht gleichzeitig den SoC aller 3 Fahrzeuge liefern.
Die Annahme "evcc pollt alle 3 Fahrzeuge parallel" ist nicht haltbar.

## Requirement-Status

| Req | Beschreibung | Status | Grund |
|-----|-------------|--------|-------|
| EVCC-01 | LP-Konfiguration fuer 3 EVs auf 1 Wallbox | PASS | Funktioniert mit Vehicle-Switching |
| EVCC-02 | SoC fuer Kia ohne Wallbox | FAIL | Nur fuer zugewiesenes Fahrzeug moeglich |
| EVCC-03 | SoC fuer Renault ohne Wallbox | FAIL | Gleiche Limitation wie EVCC-02 |
| EVCC-04 | Vehicle-Wechsel am LP korrekt | PASS | SoC wechselt mit (loadpoint-gebunden) |
| EVCC-05 | Rate-Limiting stabil | NOT TESTED | 48h-Lauf nicht durchgefuehrt |

## Go/No-Go Entscheidung

### NO-GO fuer Phase 18 (Vehicle Polling Migration)

**Begruendung:** evcc kann architekturbedingt nicht alle 3 Fahrzeuge gleichzeitig
mit aktuellem SoC versorgen. Eine Migration wuerde SmartLoads Multi-Vehicle-Faehigkeit
einschraenken — nur 1 von 3 Fahrzeugen haette aktuellen SoC.

### Entscheidung: Eigenes Cloud-Polling beibehalten (Option C)

SmartLoad behaelt das eigene Vehicle Cloud-Polling (KiaProvider, RenaultProvider):
- Unabhaengig von evcc-Limitationen
- Alle 3 Fahrzeuge haben gleichzeitig aktuellen SoC
- Phase 17.1 Bugfixes (evcc retry, staleness, thread safety) verbessern die Zuverlaessigkeit
- Phase 18 (Migration) und Phase 19 (Provider Cleanup) entfallen

### Auswirkung auf Roadmap

- **Phase 18 (Vehicle Polling Migration):** CANCELLED
- **Phase 19 (Provider Cleanup):** CANCELLED
- **Phase 20 (Tech Debt):** Bleibt bestehen, rueckt vor
- v1.3 Milestone-Scope reduziert sich auf: Phase 17 (Validierung) + Phase 17.1 (Bugfixes) + Phase 20 (Tech Debt)

## Quellen

- [evcc Loadpoints Configuration](https://docs.evcc.io/en/docs/reference/configuration/loadpoints)
- [evcc Vehicles Configuration](https://docs.evcc.io/en/docs/reference/configuration/vehicles)
- [GitHub Issue #20073](https://github.com/evcc-io/evcc/issues/20073) — vehicleSoc nur bei connected Vehicle
- [GitHub Issue #23419](https://github.com/evcc-io/evcc/issues/23419) — Vehicle-Daten nur bei LP-Zuweisung
- [GitHub Discussion #2339](https://github.com/evcc-io/evcc/discussions/2339) — poll.mode: always Diskussion

---
*Validierungsbericht erstellt: 2026-03-20*
