# EVCC-Smartload v6.1 — Predictiver LP+RL Optimizer

**Intelligente Erweiterung zu [evcc](https://evcc.io) als Home Assistant Add-on** — optimiert Hausbatterie und EV-Ladung anhand dynamischer Strompreise, 24h LP-Prognose, Solar- und Verbrauchsvorhersagen sowie Fahrer-Präferenzen.

## Verhältnis zu evcc

[evcc](https://github.com/evcc-io/evcc) ist das Open-Source Lade- und Energiemanagement-System, das Wallboxen steuert, PV-Daten liest und Stromtarife bereitstellt. **SmartLoad ersetzt evcc nicht, sondern erweitert es:**

| | evcc (Basis) | SmartLoad (Erweiterung) |
|---|---|---|
| **Steuerung** | Wallbox, Batterie, Loadpoints | Setzt evcc-Lademodi via REST API |
| **Daten** | PV, Tarife, Batterie-SoC, Loadpoints | Liest alles von evcc, ergänzt Vehicle-API-Polling |
| **Optimierung** | Reaktiv (aktueller PV-Überschuss) | Prädiktiv (24h LP-Planung mit Prognosen) |
| **Planung** | Kein Vorausblick | 96-Slot Rolling-Horizon LP (scipy/HiGHS) |
| **Prognose** | — | Verbrauchs-EMA + PV-Forecast + Preis-Perzentile |
| **Multi-EV** | 1 Loadpoint = 1 Fahrzeug | Charge-Sequencer koordiniert mehrere EVs |
| **UI** | evcc Web-UI (:7070) | Eigenes Dashboard (:8099) mit Gantt, Fahrzeuge, Lernen |

**Voraussetzung:** evcc muss installiert und konfiguriert sein (Wallbox, PV-Anlage, Stromtarif, Batterie).

## Features

| Feature | Details |
|---|---|
| **24h LP-Planner** | Rolling-Horizon LP (scipy/HiGHS) optimiert Battery+EV gemeinsam über 96 Slots (15-Min) |
| **Verbrauchsprognose** | Hour-of-day EMA aus InfluxDB-Historie, persistentes Modell, Echtzeit-Korrektur |
| **PV-Prognose** | evcc Solar Tariff API, Rolling Correction [0.3–3.0], stündliche Aktualisierung |
| **evcc Lademodus-Steuerung** | SmartLoad setzt aktiv PV/Min+PV/Schnell je nach LP-Plan und Preis-Perzentilen |
| **Override-Detection** | Manuelle evcc-Modus-Änderungen werden erkannt und respektiert bis Vorgang abgeschlossen |
| **Battery Arbitrage** | LP-gated Batterie→EV Entladung mit 7-Gate Logik und Profitabilitätsprüfung |
| **Vehicle SoC Polling** | Zuverlässige API-Provider (Kia, Renault) mit Backoff, evcc-Live-Suppression |
| **Poll Now Button** | Manueller SoC-Abruf pro Fahrzeug im Dashboard mit 5-Min Throttle |
| **StateStore** | Thread-safe RLock, atomare Snapshots, SSE-Broadcast |
| **SSE Live-Updates** | /events Endpoint, kein Polling, 30s Keepalive |
| **Config Validation** | Startup-Prüfung, HTML-Fehlerseite bei kritischen Fehlern |
| **Percentil-Thresholds** | Batterie+EV laden in günstigsten P20/P30/P40-Fenstern statt statischer ct-Grenze |
| **Hybrid LP+RL** | Linear Programming als Basis, Reinforcement Learning lernt dazu (7×5=35 Aktionen) |
| **Charge-Sequencer** | Koordiniert mehrere EVs an einer Wallbox mit Quiet Hours (21–06 Uhr) |
| **Telegram-Notifications** | Fahrer werden direkt gefragt: "Auf wieviel % laden?" → Inline-Buttons |
| **Solar-Integration** | PV-Prognose beeinflusst Lade-Aggressivität und Entladetiefe |
| **Vehicle Providers** | KIA (ccapi), Renault (renault-api), evcc, Manual, Custom |
| **Dashboard** | 4 Tabs (Status, Plan/Gantt, Fahrzeuge, Lernen) mit SVG-Charts und Live-SSE-Updates |

## Installation

1. **evcc einrichten** — [evcc.io/docs](https://docs.evcc.io) (Wallbox, PV, Batterie, Stromtarif konfigurieren)

2. Repository als Custom Add-on in Home Assistant hinzufügen:
   `Einstellungen → Add-ons → Add-on Store → ⋮ → Custom repositories`
   URL: `https://github.com/Krinco1/HA_Addon_EVCC-Smartload`

3. Add-on installieren und `evcc_url` konfigurieren (z.B. `http://evcc.local:7070`)

4. Starten — Dashboard öffnen: `http://homeassistant:8099`

## Konfiguration

### config.yaml (Add-on Optionen)

```yaml
evcc_url: "http://evcc.local:7070"     # evcc REST API Adresse (Pflicht)
battery_capacity_kwh: 33.1
battery_charge_power_kw: 5.0             # Max Ladeleistung Batterie in kW
battery_min_soc: 10                      # Min SoC in % (LP-Untergrenze)
battery_max_soc: 90                      # Max SoC in % (LP-Obergrenze)
battery_max_price_ct: 25.0              # Hard-Ceiling — kein Laden teurer als das
battery_charge_efficiency: 0.92         # Lade-Effizienz Hausbatterie
battery_discharge_efficiency: 0.92      # Entlade-Effizienz Hausbatterie
battery_to_ev_min_profit_ct: 3.0        # Min. Ersparnis für Batterie→EV (ct/kWh)
battery_to_ev_dynamic_limit: true       # Dynamisches Floor-SoC Limit
battery_to_ev_floor_soc: 20             # Min. Batterie-SoC für Batterie→EV (%)
feed_in_tariff_ct: 7.0                   # Einspeisevergütung ct/kWh
ev_max_price_ct: 30.0
ev_default_energy_kwh: 60              # Default EV-Kapazität wenn unbekannt
vehicle_poll_interval_minutes: 60       # Globales SoC-Poll-Intervall (Minuten)
quiet_hours_enabled: true               # Kein EV-Wechsel nachts
quiet_hours_start: 21
quiet_hours_end: 6
sequencer_enabled: true                 # Charge Sequencer aktiv
sequencer_default_charge_power_kw: 11.0 # Default Ladeleistung EV
```

### vehicles.yaml (Fahrzeug-APIs)

Wird beim ersten Start unter `/config/vehicles.yaml` angelegt (Beispieldatei):

```yaml
vehicles:
  - name: KIA_EV9
    type: kia
    username: "..."
    password: "..."
    capacity_kwh: 99.8

  - name: my_Twingo
    type: evcc           # SoC direkt von evcc
    capacity_kwh: 22
```

### drivers.yaml (optional)

Für Telegram-Notifications unter `/config/drivers.yaml`:

```yaml
# Bot erstellen: @BotFather in Telegram → /newbot
telegram_bot_token: "123456:ABC-DEF..."

drivers:
  - name: "Nico"
    vehicles: ["KIA_EV9"]
    telegram_chat_id: 123456789    # /start im Bot, dann getUpdates

  - name: "Fahrer2"
    vehicles: ["ora_03", "my_Twingo"]
    telegram_chat_id: 987654321
```

**Ohne `drivers.yaml`**: System läuft vollständig ohne Notifications — EV-Ladung mit statischen Limits wie in v4.

## API-Endpunkte

| Methode | Endpoint | Beschreibung |
|---|---|---|
| GET | `/` | Dashboard (HTML) |
| GET | `/health` | Heartbeat — `{"status":"ok","version":"6.1.1"}` |
| GET | `/status` | Vollständiger System-Status inkl. Percentile, RL-Reife |
| GET | `/summary` | Kompakte Übersicht für externe Integrationen |
| GET | `/config` | Aktive Konfiguration (read-only) |
| GET | `/vehicles` | Alle Fahrzeuge mit SoC, Alter, Verbindungsstatus |
| GET | `/chart-data` | Preischart-Daten inkl. P30-Linie und Solar-Forecast |
| GET | `/slots` | Aktuelle Preis-Slots der nächsten 24h |
| GET | `/forecast` | 96-Slot Verbrauchs- und PV-Prognose mit Confidence |
| GET | `/events` | SSE-Stream für Live-Updates (Server-Sent Events) |
| GET | `/sequencer` | Lade-Zeitplan + offene Anfragen + Quiet Hours |
| GET | `/drivers` | Fahrer-Status (kein Telegram-Token/Chat-ID) |
| GET | `/decisions` | Letzte 40 Entscheidungen aus dem Decision-Log |
| GET | `/comparisons` | LP-vs-RL Vergleichsstatistiken der letzten 50 Runs |
| GET | `/strategy` | Aktuelle Strategie-Erklärung (Batterie + EV) |
| GET | `/rl-devices` | RL-Modus und Lern-Fortschritt pro Gerät |
| GET | `/rl-learning` | RL-Lernstatistiken und Trainingsfortschritt |
| GET | `/rl-audit` | RL Constraint Audit Checklist |
| GET | `/mode-control` | **v6.1** Lademodus-Status (Modus, Override, evcc-Erreichbarkeit) |
| GET | `/plan` | Aktueller 24h-Plan mit Slot-Details und Erklärungen |
| GET | `/history` | Plan-vs-Ist Vergleichsdaten |
| GET | `/docs` | Eingebaute Dokumentation (HTML) |
| GET | `/docs/api` | API-Referenz (HTML) |
| POST | `/vehicles/manual-soc` | Manuellen SoC setzen `{"vehicle":"KIA_EV9","soc":45}` |
| POST | `/vehicles/refresh` | **v6.1** Poll Now — sofortiger SoC-Abruf (5 Min Throttle) |
| POST | `/sequencer/request` | Lade-Anfrage stellen `{"vehicle":"...","target_soc":80}` |
| POST | `/sequencer/cancel` | Lade-Anfrage abbrechen `{"vehicle":"..."}` |
| POST | `/override/boost` | Sofort-Ladung erzwingen |
| POST | `/override/cancel` | Override abbrechen |
| POST | `/rl-override` | RL-Modus für ein Gerät überschreiben |

## Architektur

```
evcc (Basis-System)
  │
  │  REST API (:7070)
  │  ├── /api/state          → Batterie, PV, Grid, Loadpoints
  │  ├── /api/tariff/grid    → Dynamische Strompreise (24h)
  │  ├── /api/tariff/solar   → PV-Ertragsprognose
  │  └── /api/loadpoints/…   → Lademodus setzen (pv/minpv/now)
  │
  ▼
SmartLoad (Erweiterung)
  │
  ├── DataCollector          → Liest evcc-State alle 30s
  ├── ConsumptionForecaster  → Verbrauchsprognose aus InfluxDB
  ├── PVForecaster           → PV-Prognose via evcc Solar Tariff
  │
  ├── HorizonPlanner (LP)    → 96-Slot Rolling-Horizon Optimierung
  │     ↓
  ├── EvccModeController     → Setzt evcc-Lademodus (pv/minpv/now)
  ├── BatteryArbitrage       → 7-Gate Batterie→EV Entladung
  ├── ChargeSequencer        → Multi-EV Koordination
  │
  ├── StateStore             → Thread-safe State + SSE-Broadcast
  └── Dashboard (:8099)      → 4 Tabs mit Live-Updates
```

Der **HorizonPlanner** löst jeden 15-Min-Zyklus ein 96-Slot LP (MPC-Ansatz): Nur die Slot-0-Entscheidung wird angewendet; im nächsten Zyklus wird das LP mit dem tatsächlichen SoC neu gelöst.

Der **EvccModeController** setzt den evcc-Lademodus über die evcc REST API basierend auf dem LP-Plan und Preis-Perzentilen. Manuelle evcc-Overrides werden erkannt und respektiert bis der Ladevorgang endet.

Die **BatteryArbitrage** prüft über 7 Gates ob Batterie→EV-Entladung wirtschaftlich sinnvoll ist (inkl. LP-Autorisierung, Profitabilität, 6h-Lookahead-Guard).

## Wichtige Hinweise

- **evcc ist Pflicht** — SmartLoad funktioniert nicht ohne eine laufende evcc-Instanz
- **evcc bleibt Steuerungsschicht** — SmartLoad sendet Befehle über die evcc API, steuert nie direkt Hardware
- **Manuelle evcc-Overrides** werden respektiert — SmartLoad kämpft nicht gegen den Nutzer
- **HorizonPlanner ist primärer Optimizer (LP)**; HolisticOptimizer nur automatischer Fallback bei LP-Fehler
- **Forecaster brauchen 24h Daten** bevor sie bereit sind (is_ready Gate) — davor läuft LP ohne Prognose
- **Vehicle Providers**: Kia/Renault-API mit automatischem Backoff, evcc-Live-SoC hat Vorrang bei Wallbox-Verbindung
- **Quiet Hours**: Zwischen 21:00–06:00 kein automatisches EV-Umstecken
- **Telegram**: Direkte Bot API, kein HA Automation/Webhook nötig
- **drivers.yaml optional**: Ohne Datei volles Bestandsverhalten

## Links

- **evcc Projekt:** [evcc.io](https://evcc.io) / [GitHub](https://github.com/evcc-io/evcc) / [Docs](https://docs.evcc.io)
- **SmartLoad Dashboard:** `http://homeassistant:8099`
- **SmartLoad Docs:** `http://homeassistant:8099/docs`
- **GitHub:** [Krinco1/HA_Addon_EVCC-Smartload](https://github.com/Krinco1/HA_Addon_EVCC-Smartload)
