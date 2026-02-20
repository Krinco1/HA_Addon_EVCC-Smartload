# Changelog

## [5.0.1] – 2026-02-20

### Fixed
- **`No module named 'yaml'`** — `pyyaml` zu pip-Dependencies im Dockerfile hinzugefügt
- **`SystemState() missing 'ev_power'`** — Pflichtfeld im DataCollector-Konstruktor ergänzt (`ev_power=0.0`)
- **`InfluxDBClient has no attribute 'get_history_hours'`** — Methode `get_history_hours()` in `influxdb_client.py` implementiert
- **`DriverManager.to_api_list()`** — Methode fehlte, wird von `web/server.py` unter `/drivers` aufgerufen

## [5.0.0] – 2026-02-20

### Neu
- **Percentil-Thresholds** statt statischer ct-Grenzen (P20/P30/P40/P60/P80)
- **RL State Space**: 25 → 31 Features (Percentile, Spread, günstige Stunden, Solar-Prognose, Saison)
- **RL Action Space**: 16 → 35 Aktionen (7 Batterie × 5 EV-Modi)
- **Charge Sequencer** (`charge_sequencer.py`): Koordinierte Lade-Reihenfolge für mehrere EVs
- **Quiet Hours** (Standard: 21:00–06:00): Kein EV-Wechsel während der Nacht
- **Telegram Notifications** (`notification.py`): Direkte Bot-API, kein HA-Umweg
- **Driver Manager** (`driver_manager.py`): Fahrer-EV-Zuordnung via `drivers.yaml`
- **Neue API-Endpunkte**: `/sequencer`, `/drivers`, `/sequencer/request`, `/sequencer/cancel`
- **Dashboard**: P30-Linie im Preischart, Lade-Zeitplan-Panel, Sequencer-Status

### Geändert
- `battery_power` und `grid_power` fehlen nicht mehr optional in SystemState
- LP Optimizer auf Percentil-basierte Thresholds umgestellt
- RL Q-Table wird zurückgesetzt (State Space inkompatibel mit v4) — RL lernt in ~2 Tagen vom LP nach

### Neue Konfigurationsfelder (alle optional, Defaults = bisheriges Verhalten)
```yaml
quiet_hours_enabled: true   # Kein EV-Wechsel 21:00–06:00
quiet_hours_start: 21
quiet_hours_end: 6
sequencer_enabled: true     # Koordiniertes EV-Laden
```

### Neue Datei: `/config/drivers.yaml`
```yaml
telegram_bot_token: ""
drivers:
  - name: "Nico"
    vehicles: ["KIA_EV9"]
    telegram_chat_id: 123456789
```

### Rückwärtskompatibilität
- `vehicles.yaml` Format unverändert
- Alle bestehenden `config.yaml` Felder bleiben
- Ohne `drivers.yaml` läuft alles wie in v4 (keine Notifications, statische EV-Limits)
- RL-Daten (Comparisons) bleiben erhalten; nur Q-Table wird zurückgesetzt

---

## [4.3.11] – 2026-02-18
Dashboard-Redesign, Decision-Log, SVG-Chart, Wallbox-Erkennung, W/kW-Ladeplanung

## [4.3.9] – 2026-02-15
PV-Ladeplanung, Energiebilanz, KIA-Fix, Solar-Surplus-Berechnung

## [4.3.7] – 2026-02-12
Batterie-Entladung für EV, bufferSoc/prioritySoc API, Dashboard-Farbzonen
