# EVCC-Smartload Add-on Repository

Home Assistant Add-on Repository für **EVCC-Smartload** — eine intelligente Erweiterung zu [evcc](https://evcc.io) für prädiktives Energiemanagement mit 24h LP-Planner, PV/Verbrauchs-Prognose und hybridem LP+RL Optimizer.

## Was ist evcc?

[evcc](https://github.com/evcc-io/evcc) ist ein Open-Source Lade- und Energiemanagement-System für Elektrofahrzeuge und Hausbatterien. Es steuert Wallboxen, liest PV-Daten und Stromtarife, und bietet eine Web-UI zur Überwachung.

**SmartLoad baut auf evcc auf** und erweitert es um:
- Prädiktive 24h-Optimierung (statt reaktiver Steuerung)
- LP-basierte kostenoptimale Lade-/Entladeplanung
- Verbrauchs- und PV-Prognosen aus historischen Daten
- Intelligente Multi-EV-Koordination an einer Wallbox
- Automatische evcc-Lademodus-Steuerung basierend auf Preis-Perzentilen
- Batterie→EV Arbitrage mit 7-Gate Sicherheitslogik

evcc bleibt die zentrale Datenquelle (Strompreise, PV, Batterie-Status, Wallbox) und Steuerungsschnittstelle — SmartLoad liest Daten über die evcc REST API und setzt Lademodi über dieselbe API.

## Installation

**Voraussetzung:** [evcc](https://evcc.io) muss installiert und konfiguriert sein (Wallbox, PV, Batterie, Stromtarif).

1. Dieses Repository als Custom Add-on Repository in Home Assistant hinzufügen:

   **Einstellungen** → **Add-ons** → **Add-on Store** → **⋮** (oben rechts) → **Repositories**

   URL einfügen:
   ```
   https://github.com/Krinco1/HA_Addon_EVCC-Smartload
   ```

2. Add-on Store aktualisieren (Seite neu laden)

3. **EVCC-Smartload - Predictive LP Optimizer** installieren

4. `evcc_url` in der Add-on-Konfiguration auf die evcc-Instanz setzen (z.B. `http://evcc.local:7070`)

5. Starten — SmartLoad verbindet sich mit evcc und beginnt die Optimierung

## Enthaltene Add-ons

| Add-on | Beschreibung | Version |
|---|---|---|
| [EVCC-Smartload](evcc-smartload/) | Predictiver LP+RL Optimizer für Batterie & EV-Ladung mit 24h Horizont | 6.1.1 |

## Features

- **HorizonPlanner (24h LP)** — Rolling-Horizon LP (scipy/HiGHS) optimiert Battery+EV gemeinsam über 96 Slots (15-Min)
- **evcc Lademodus-Steuerung** — SmartLoad setzt aktiv PV/Min+PV/Schnell mit Override-Detection
- **Battery Arbitrage** — LP-gated Batterie→EV Entladung mit 7-Gate Logik
- **Verbrauchsprognose** — Hour-of-day EMA aus InfluxDB-Historie, persistentes Modell, Echtzeit-Korrektur
- **PV-Prognose** — evcc Solar Tariff API, Rolling Correction [0.3–3.0], stündliche Aktualisierung
- **Vehicle SoC Polling** — Zuverlässige API-Provider (Kia, Renault) mit Backoff und evcc-Live-Suppression
- **Poll Now** — Manueller SoC-Abruf pro Fahrzeug im Dashboard
- **StateStore (Thread-safe)** — RLock-geschützter State, atomare Snapshots, SSE-Broadcast
- **SSE Live-Updates** — /events Endpoint, kein Polling, 30s Keepalive
- **Config Validation** — Startup-Prüfung, HTML-Fehlerseite bei kritischen Fehlern
- **Percentil-Thresholds** — Batterie+EV laden in günstigsten P20/P30/P40-Fenstern
- **Hybrid LP+RL** — Linear Programming als Basis, Reinforcement Learning lernt dazu
- **Charge-Sequencer** — Koordiniert mehrere EVs an einer Wallbox mit Quiet Hours
- **Telegram-Notifications** — Fahrer werden direkt per Bot gefragt
- **Vehicle Providers** — KIA, Renault, evcc, Custom
- **Dashboard** — 4 Tabs (Status, Plan/Gantt, Fahrzeuge, Lernen) mit SVG-Charts und Live-SSE-Updates

## Zusammenspiel mit evcc

```
evcc (Basis)                          SmartLoad (Erweiterung)
┌─────────────────────┐              ┌──────────────────────────┐
│ Wallbox-Steuerung   │◄── API ────►│ HorizonPlanner (24h LP)  │
│ PV-Daten            │   lesen/    │ Verbrauchs-/PV-Prognose  │
│ Stromtarife         │   setzen    │ EvccModeController       │
│ Batterie-Status     │              │ BatteryArbitrage         │
│ Loadpoint-Modes     │              │ Charge-Sequencer         │
│ Web-UI              │              │ Dashboard (:8099)        │
└─────────────────────┘              └──────────────────────────┘
```

SmartLoad greift ausschließlich über die evcc REST API zu — keine Modifikation an evcc nötig.

## Links

- **SmartLoad Dashboard:** `http://homeassistant.local:8099`
- **evcc Projekt:** [evcc.io](https://evcc.io) / [GitHub](https://github.com/evcc-io/evcc)
- **SmartLoad GitHub:** [Krinco1/HA_Addon_EVCC-Smartload](https://github.com/Krinco1/HA_Addon_EVCC-Smartload)
