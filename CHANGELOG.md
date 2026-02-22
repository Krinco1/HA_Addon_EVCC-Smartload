# EVCC-Smartload Changelog

---

## v5.0.3 — Bugfixes: Dashboard · Notifications · RL-Feature · Codebereinigung

### Bugfixes

**notification.py: TypeError durch naive Timestamps**
- `datetime.now()` (ohne Timezone) wurde für Throttle-Vergleiche und `get_pending()` verwendet
- Verursachte `TypeError: can't subtract offset-naive and offset-aware datetimes` bei Telegram-Anfrage-Throttling
- Fix: Alle `datetime.now()` → `datetime.now(timezone.utc)` für Konsistenz mit dem Rest der Codebase

**Dashboard: Sequencer-Panel komplett defekt (nicht sichtbar, Datenformat-Fehler)**
- `renderSequencer()` behandelte `requests` als Array, aber API liefert ein Dict (Fahrzeugname → Daten)
- `data.is_quiet_now` existiert nicht — korrekter Pfad ist `data.quiet_hours.currently_active`
- `data.pre_quiet_recommendation` existiert nicht — korrekter Pfad ist `data.quiet_hours.pre_quiet_recommendation`
- Sequencer-Karte (`display:none`) wurde nie eingeblendet, selbst wenn Daten vorhanden
- Card-Inhalt wurde bei jedem Render komplett überschrieben (inkl. Quiet-Badge), statt nur den Content-Bereich
- Fix: Dict→Array Konvertierung, korrekte API-Pfade, `card.style.display = ''`, Render in `#seqRequests` statt Card-Overwrite

**Dashboard: P30-Linie im Preischart nie gezeichnet**
- Chart-Code suchte `data.percentiles[30]` — dieses Feld existierte nicht in der `/chart-data` API
- P30 wurde mit `* 100` konvertiert (EUR→ct), aber war nie vorhanden
- Fix: `p30_ct` in Chart-Data API ergänzt, Chart-Code nutzt `data.p30_ct` direkt (bereits in ct)

**Dashboard: Quiet-Hours in Konfig-Tabelle falsch angezeigt**
- `cfg.quiet_hours` existiert nicht — korrekte Felder sind `cfg.quiet_hours_start` / `cfg.quiet_hours_end`
- Fix: Ruhezeit zeigt nun dynamisch `start:00–end:00` aus tatsächlicher Konfiguration

**vehicle_monitor.py: EV-Ladeleistung (ev_power) nicht erfasst**
- `SystemState.ev_power` (RL-Feature Index 8) war immer 0, da `chargePower` nicht aus evcc-Loadpoint gelesen wurde
- RL-Agent konnte nie lernen, ob das EV gerade lädt oder nicht (Feature-Vektor unvollständig)
- Fix: `chargePower` aus evcc-Loadpoint auslesen und in `ev_power` schreiben

**web/server.py: Inkonsistente Timestamps in API-Responses**
- `/status`, `/vehicles`, `/rl-devices` nutzten `datetime.now()` (naive, Lokalzeit) statt UTC
- Fix: Alle API-Timestamps auf `datetime.now(timezone.utc).isoformat()` vereinheitlicht

### Codebereinigung

**state.py: Unbenutzte `VehicleStatus`-Klasse entfernt**
- Duplizierte `VehicleData` aus `vehicles/base.py` mit leicht abweichender Logik
- War nie importiert oder verwendet — Totes Code seit v4 → entfernt

**evcc_client.py: Unbenutzter `import re` entfernt**
- `import re as _re` war innerhalb der Tarif-Parsing-Schleife definiert, aber nie referenziert

**main.py: Unbenutzte Variable `now_utc` entfernt**
- Variable wurde zugewiesen aber nie gelesen (Überbleibsel aus Refactoring)

**vehicle_monitor.py: `ev_name` None-Safety**
- `ev_name=ev_name` konnte `None` sein, obwohl `SystemState.ev_name` ein `str` erwartet
- Fix: `ev_name=ev_name or ""`

### Neue Konfigurationsfelder
```yaml
sequencer_enabled: true         # Default: true — Multi-EV Ladeplanung aktivieren
decision_interval_minutes: 15   # Default: 15 — Optimierungs-Zyklus in Minuten
```

### Geänderte Dateien
- `rootfs/app/notification.py` — Timezone-Fix für Telegram-Throttling
- `rootfs/app/web/static/app.js` — Sequencer-Panel, P30-Chart, Quiet-Hours-Config
- `rootfs/app/web/server.py` — P30 in Chart-Data API, konsistente UTC-Timestamps
- `rootfs/app/state.py` — Unbenutzte VehicleStatus-Klasse entfernt
- `rootfs/app/vehicle_monitor.py` — ev_power aus evcc, ev_name None-Safety
- `rootfs/app/evcc_client.py` — Unbenutzter Import entfernt
- `rootfs/app/main.py` — Unbenutzte Variable entfernt
- `config.yaml` — Fehlende Schema-Felder ergänzt, Version 5.0.3
- `rootfs/app/version.py` — 5.0.3

### Rückwärtskompatibilität
- Alle Fixes sind transparent — keine Konfigurationsänderungen nötig
- `sequencer_enabled` und `decision_interval_minutes` sind optional (Defaults beibehalten)
- RL Q-Table wird NICHT zurückgesetzt (State-Space unverändert bei 31 Features)

---

## v5.0.2 — Bugfixes: ManualSocStore · InfluxDB SSL

### Bugfixes

**ManualSocStore.get() gab dict statt float zurück**
- `set()` speichert `{"soc": 80, "timestamp": "..."}`, aber `get()` gab das gesamte dict zurück
- Verursachte `TypeError: '>' not supported between instances of 'dict' and 'int'` in:
  - `vehicle_monitor.py:102` (predict_charge_need)
  - `comparator.py:194` (EV-SoC Vergleiche)
  - `web/server.py` (API-Responses)
  - `main.py:276` (Hauptschleife)
- Fix: `get()` extrahiert jetzt den `soc`-Wert als float
- Zusätzlich: `get_timestamp()` Methode für sauberen Timestamp-Zugriff
- Defensive Absicherung in `get_effective_soc()` gegen dict-Typ

**InfluxDB SSL-Support**
- InfluxDB-Client war hardcoded auf `http://` — bei aktiviertem SSL im InfluxDB-Addon kam HTTP 401
- Neue Config-Option `influxdb_ssl: true/false` (Default: false)
- SSL-Kontext akzeptiert selbstsignierte Zertifikate (lokales Netzwerk)
- Protokoll-Erkennung beim Start geloggt

### Geänderte Dateien
- `rootfs/app/state.py` — ManualSocStore.get() + get_timestamp() + defensive get_effective_soc()
- `rootfs/app/influxdb_client.py` — SSL-Support mit konfigurierbarem Protokoll
- `rootfs/app/config.py` — neues Feld `influxdb_ssl: bool`
- `config.yaml` — Option `influxdb_ssl` + Schema-Eintrag
- `rootfs/app/version.py` — 5.0.2

### Neue Konfigurationsfelder
```yaml
influxdb_ssl: true   # Default: false — auf true setzen wenn InfluxDB SSL aktiviert hat
```

### Rückwärtskompatibilität
- `influxdb_ssl` Default ist `false` → bestehende HTTP-Setups unverändert
- ManualSocStore-Fix ist transparent — bestehende JSON-Daten werden korrekt gelesen

---

## v5.0.0 — Percentil-Optimierung · Charge-Sequencer · Telegram

### Neue Features

**Percentil-basierte Preis-Thresholds (LP + RL)**
- Batterie und EVs laden nicht mehr gegen statische ct-Schwellen, sondern gegen dynamische Marktperzentile
- LP-Optimizer berechnet P20/P40/P60/P80 aus den nächsten 24h und wählt Aggressivität je nach Solar-Prognose, SoC und Saison
- RL-Agent bekommt 6 neue State-Features: P20, P60, Spread, günstige Stunden, Solar-Forecast, Saisonindex
- State Space: 25 → 31 Features · Action Space: 7×5 = 35 Aktionen (war 4×4 = 16)
- P30-Linie im Dashboard-Chart (cyan gestrichelt) zeigt günstigstes 30%-Fenster

**Charge-Sequencer (EV-Lade-Koordination)**
- Plant optimale Lade-Reihenfolge für mehrere EVs an einer Wallbox
- Quiet Hours: Kein EV-Wechsel zwischen 21:00–06:00 (konfigurierbar)
- Pre-Quiet-Hour-Empfehlung: 90 Minuten vorher wird empfohlen, welches EV angesteckt werden soll
- Dashboard zeigt Lade-Zeitplan mit Stunden, kWh, Preisen und Quelle (Solar/Günstig/Normal)
- Neuer API-Endpoint: `GET /sequencer`, `POST /sequencer/request`, `POST /sequencer/cancel`

**Telegram-Notifications (direkt, kein HA-Umweg)**
- Smartload → Telegram Bot API → Fahrer (kein HA Webhook/Automation nötig)
- Long-Polling Thread für Antworten (Inline-Keyboard: 80% / 100% / Nein)
- Fahrer bestätigt Ziel-SoC per Button → Sequencer plant automatisch
- Konfiguration über neue `drivers.yaml` (analog zu `vehicles.yaml`)
- Notification bei: Preisfenster öffnet, Ladung fertig, Umsteck-Empfehlung

**Driver Manager (drivers.yaml)**
- Neue optionale Konfigurationsdatei `/config/drivers.yaml`
- Fahrer ↔ Fahrzeug-Zuordnung + Telegram Chat-IDs
- Beim ersten Start wird `drivers.yaml.example` angelegt
- Neuer API-Endpoint: `GET /drivers`

### Geänderte Konfigurationsfelder
Neue optionale Felder in `config.yaml` (Defaults = Bestandsverhalten):
```yaml
quiet_hours_enabled: true   # Standard: true
quiet_hours_start: 21       # Ab wann kein EV-Wechsel
quiet_hours_end: 6          # Bis wann kein EV-Wechsel
```

### Rückwärtskompatibilität
- Alle bestehenden `config.yaml`-Felder bleiben unverändert
- `vehicles.yaml` Format bleibt identisch
- `drivers.yaml` ist optional — ohne Datei läuft alles wie bisher
- Ohne Telegram-Token: keine Notifications, EV mit statischen Limits (wie v4)
- RL Q-Table Reset notwendig (State Space ändert sich) — RL lernt in ~2 Tagen vom LP neu

### Was sich NICHT ändert
- Dashboard URL: `http://homeassistant:8099`
- Alle bestehenden API-Endpunkte
- Vehicle Providers (KIA, Renault, Custom, Manual, evcc)
- SVG-Chart, Energiebilanz, Decision Log
- RL Device Control pro Gerät
- Batterie→EV Entladung
- ManualSocStore, InfluxDB, Docker-Struktur

---

## v4.3.11 — SVG-Chart Redesign · Dashboard-Verbesserungen
- SVG-Preischart vollständig neu (Y-Achse, Gitter, Solar-Fläche, Tooltip)
- Batterie-Entladetiefe mit dynamischem bufferSoc via evcc API
- Energiebilanz mit Echtzeit-Werten (PV, Haus, Netz, Batterie)
- Decision-Log mit Kategorien (observe, plan, action, warning, rl)

## v4.3.x — Batterie→EV Entladung · Dynamic Discharge
- evcc bufferSoc/prioritySoc/bufferStartSoc dynamisch berechnet
- Solar-Prognose-Integration für Entladetiefenberechnung
- Case-insensitive Fahrzeug-Matching korrigiert
- RL Pro-Device Control (Batterie + EVs einzeln steuerbar)

## v4.0.0 — Hybrid LP+RL
- Dualer Optimierungsansatz: Linear Programming + Reinforcement Learning
- Comparator: automatischer LP↔RL Switch nach Leistungsmetriken
- Neue Dashboard-Panels: RL-Reife, Vergleiche, Entscheidungs-Log
