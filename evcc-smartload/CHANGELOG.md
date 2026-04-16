# EVCC-Smartload Changelog

---

## v6.3.2 — Boost & Twingo Hotfix (2026-04-16)

**Zwei vom User gemeldete Folge-Regressionen aus v6.3.1.**

### Boost funktioniert wieder während der Quiet-Hours

- `override_manager.activate()` pruefte `_is_quiet(now)` und brach Boost lautlos ab,
  sobald die aktuelle lokale Stunde in der konfigurierten Ruhezeit lag (21-06).
  Vor v6.3.1 hatte der UTC-Timezone-Bug diesen Check faktisch deaktiviert (UTC 22:00
  = 20:00 lokal im Sommer → nicht in Quiet Hours → Boost ging). Mit dem 6.3.1-
  Lokalzeit-Fix wurde der Block endlich scharf — aber der Block selbst war die
  falsche Design-Entscheidung: ein expliziter Boost-Klick ist ein "Ich brauche
  jetzt Strom" vom User und muss Schedule-Constraints brechen.
- Fix: Quiet-Hours-Block in `override_manager.activate()` komplett entfernt.
  Quiet Hours gelten weiter nur fuer den automatischen Sequencer-EV-Wechsel.

### Twingo (Renault) Provider — Cross-Loop-Bug

- `aiohttp.ClientSession` ist an den asyncio-Loop gebunden, in dem sie erzeugt wurde.
  Der Code erzeugte Loop und Session getrennt: bei "Poll Now" (force=True) wurde
  nur der Client resetted, nicht die Session → neuer Client kam mit alter Session
  → aiohttp warf "attached to a different loop" oder still failing requests. Beim
  Loop-Recreate (nach is_closed) wurde die alte Session ebenfalls liegengelassen.
- Fix in `vehicles/renault_provider.py`:
  - Loop + Session + Client werden immer gemeinsam recreated.
  - `asyncio.set_event_loop(self._loop)` gesetzt (noetig bei Python 3.14/Alpine).
  - Beim `force`-Refresh wird die alte Session im alten Loop sauber geschlossen.
  - Bei jedem Poll-Fehler wird die Session gedroppt, damit der naechste Poll frisch startet.

### Tests

- 101/101 Unit Tests gruen, keine Regressionen.

---

## v6.3.1 — Code-Review Bugfixes (2026-04-16)

Umfangreicher Bugfix-Release nach 5-Perspektiven Code-Review
(Claude Opus + GPT-5 + Gemini 3.1 Pro Cross-AI Review, ~120 Findings).
Viele Komponenten liefen seit v1.3 fehlerhaft ohne sichtbare Fehlermeldung.

### CRITICAL Fixes (Production Bugs)

**Main-Loop Crash bei aktivem Sequencer**
- `decision_log.log_main_cycle` iterierte `get_requests_summary()` als Dict,
  Methode liefert aber seit Phase 7 eine Liste. Wirft AttributeError in jedem Cycle
  sobald ein Charge-Request existiert → Main-Loop sprang in Exception-Handler.
  Fix: iteriert jetzt die Liste direkt (`decision_log.py:170`).

**EvccModeController sendete an falschen Loadpoint**
- `_apply_mode()` verwendete `lp_id=0` — evcc REST-API ist aber 1-basiert
  (Sequencer/OverrideManager nutzten korrekt `lp_id=1`). Alle Mode-Kommandos
  feuerten 404 → Mode-Steuerung funktionierte nie.
  Fix: konstante `LOADPOINT_ID = 1`; Test angepasst (`evcc_mode_controller.py:227`).

**Sequencer cancelte aktive Boost-Overrides**
- `main.py` rief `sequencer.apply_to_evcc()` auch wenn ein Boost-Override
  aktiv war. Der Sequencer setzte den Loadpoint je nach Schedule auf `off` oder
  anderen Modus und killte den gerade gestarteten Boost sofort.
  Fix: Sequencer-Apply wird bei aktivem Override uebersprungen (`main.py:684`).

**PV-Unit-Heuristik zerstoerte Forecast-Korrektur**
- `pv_kw = pv_power / 1000 if pv_power > 100 else pv_power` — bei Daemmerung
  (z.B. 50 W) wurde "50" als 50 kW an den Forecaster weitergereicht.
  Korrekturkoeffizient wurde auf 3.0 geclampt → alle PV-Forecasts um Faktor 3
  ueberschaetzt → LP-Plaene systematisch falsch.
  Fix: `pv_power / 1000.0` immer (`main.py:364`).

### HIGH Fixes (Funktional kaputt)

**Quiet-Hours & Override-Manager in UTC statt Lokalzeit**
- Alpine Container laeuft in UTC. `quiet_hours_start=21` wurde als 21:00 UTC
  interpretiert → Ruhezeiten schalten in DE 1-2h zu spaet/frueh.
  Fix: neues Modul `time_util.py` mit `local_hour()` / `local_now()` via
  `ZoneInfo(TZ-env || Europe/Berlin)`. Angewendet in `charge_sequencer._is_quiet`,
  `charge_sequencer.get_pre_quiet_recommendation`, `override_manager._is_quiet`,
  `optimizer/holistic._assess_battery_urgency`.

**ForecastReliability nutzte falschen Slot-Index**
- `pv_96[current_slot_idx]` — aber Forecaster liefern slot 0 = "jetzt",
  nicht absolute Tagesslots. MAE wurde mit zufaellig versetzten Paaren berechnet,
  Konfidenzen rauschten. Fix: immer `pv_96[0]` / `consumption_96[0]`.

**RL lernte mit falschem Action-Index (Off-by-one-Cycle)**
- `learn_from_correction(last_state, _rl_action_idx, reward, state)` uebergab
  den Action-Idx vom AKTUELLEN Cycle, gehoert aber zum Uebergang
  `last_state → state` (voriger Cycle). Q-Values trainierten mit verdrehten
  Aktionen. Fix: `last_rl_action_idx` / `last_rl_bat_delta_ct` / `last_rl_ev_delta_ct`
  puffern und im Folgecycle im Reward-Update verwenden (`main.py:288-291, 719, 743`).

**LP-Preisarray nicht auf aktuellen 15-min-Slot aligned**
- `_tariffs_to_96slots` akzeptierte Stundentarife ab `now - 1h`, expandierte
  stumpf zu 4 Slots → `price_96[0]` trug oft den Preis der Vorstunde. Planungsfehler
  im Slot 0. Fix: Slots werden mit Zeitstempel expandiert und auf das aktuelle
  15-min-Fenster gefiltert (`optimizer/planner.py:201-217`).

### Zusaetzliche Fixes

**RL State-Features 13-24 waren konstant 0**
- `SystemState.price_forecast` und `SystemState.pv_forecast` wurden nie
  befuellt → 12 von 31 Feature-Dimensionen waren tote Bits. RL lernte in
  kollabiertem State-Space. Fix: aus `tariffs[:6]` (EUR/kWh) und `pv_96` (W) in
  der Data-Pipeline assemblieren (`main.py:373-396`).

**ev_power hardcoded auf 0.0**
- `DataCollector._collect_once` setzte `ev_power=0.0` hart, obwohl evcc
  `chargePower` liefert → History und RL-Reward-Proxy arbeiteten mit falschen
  Zahlen. Fix: `ev_power_w = float(lp.get("chargePower", 0))` (`vehicle_monitor.py:302-322`).

**`hours_cheap_remaining` zaehlte Slots statt Stunden**
- Bei 15-min-Spot-Tarifen 4× zu gross. Fix: Slot-Dauer aus `start`/`end`
  berechnen, in Stunden umrechnen (`main.py:336-352`).

**`solar_forecast_total_kwh` Unit-Detection fehlerhaft**
- `solar_today[0].value > 100` schlug vor Sonnenaufgang (0 W) fehl → Gesamtwert
  um Faktor 1000 falsch. Fix: Peak-Value statt Index 0 pruefen (`main.py:353-363`).

**HolisticOptimizer nutzt lokale Monatszeit**
- `datetime.now().month` im UTC-Container lieferte Drift am Jahreswechsel.
  Fix: `local_now().month` (`optimizer/holistic.py:237`).

**Sequencer ignorierte Abfahrts-Deadlines**
- `_assign_time_windows` plante Slots nach `departure_dt` ein. Fix: filtert
  verfuegbare Hours gegen `departure_store.get(vehicle_name)`
  (`charge_sequencer.py:275-290`).

**Arbitrage las veralteten DynamicBuffer-State**
- `run_battery_arbitrage` lief vor `buffer_calc.step()` → griff auf Daten vom
  vorigen Cycle zu. Fix: Buffer-Step vor Arbitrage (`main.py:644-660`).

**JSON-Writes ohne Atomic-Rename**
- `Comparator.save`, `ManualSocStore._save`, `DepartureTimeStore._save`
  schrieben direkt. Crash mitten im Write korrumpiert Datei. Fix: schreiben in
  `.tmp` + `os.replace()` (`comparator.py:397`, `state.py:231`, `departure_store.py:216`).

### Security Fixes

**Telegram Bot: Sender-Whitelist**
- Callbacks und Text-Nachrichten wurden ohne Sender-Pruefung verarbeitet. Jeder
  mit Bot-Kenntnis konnte `/boost` fremder Fahrzeuge ausloesen. Fix:
  `TelegramBot.authorize` Callable prueft `chat_id` gegen
  `drivers.yaml`. Unbekannte Chats werden stumm verworfen. `text_handler`-Prefix
  wird nicht mehr als Callback-Data-Match missverstanden
  (`notification.py:36-37, 100-131, 212`).

**Telegram HTML-Injection**
- `parse_mode: HTML` + User-Input aus `vehicle_name` / `driver_name` ohne
  Escaping. Fix: `_esc()` Helper auf allen user-controllable Werten
  (`notification.py:20-28` + 7 Ausgabestellen).

### Uebersprungen

- Port 8099 Ingress-Hardening: bewusste Nutzer-Entscheidung (LAN als
  vertrauenswuerdig eingestuft, 2026-04-16).
- LP Mutual-Exclusion-Constraint: Gemini 3.1 Pro bestaetigte B2-Finding als
  False-Positive (Round-trip-Efficiency ist implizit ueber SoC-Dynamik korrekt).

### Review-Reports

- `.planning/REVIEW.md` — Claude Opus: ~70 Findings (Bugs/Quality)
- `.planning/SECURITY.md` — 18 Findings (Security)
- `.planning/AI-REVIEW.md` — 28 Findings (Logic/Math)
- `.planning/GPT5-REVIEW.md` — GPT-5 Cross: 4 neue Bugs + 4 False-Positives korrigiert
- `.planning/GEMINI-REVIEW.md` — Gemini 3.1 Pro Cross: 1 False-Positive korrigiert
- `.planning/CODE-REVIEW-SUMMARY.md` — Konsolidierter Top-10 Fix-Plan

### Tests

- 101 Unit Tests bestehen (1 Test fuer lp_id=1 angepasst)

---

## v6.3.0 — Vehicle Data Reliability & Tech Debt (Milestone v1.3)

### Bugfixes (Phase 17.1)

**evcc API Client — Error Visibility + Retry**
- `get_state()` loggt jetzt Fehler statt sie stumm zu schlucken
- 1 automatischer Retry bei `ConnectionError` mit 2s Pause
- `_login()` loggt Auth-Fehler als Warning

**Vehicle Data Staleness Race**
- `update_from_evcc()` setzt `last_update` und `data_source` immer wenn Fahrzeug verbunden ist — auch bei SoC=None
- `freshness` Property konsistent mit `is_data_stale()` (beide nutzen `last_update`)

**Charge Sequencer Thread Safety**
- `threading.Lock` schuetzt alle `requests`-Dict Zugriffe
- `_urgency_reason()` nutzt `departure_store.get_raw_iso()` Public API

**DataCollector Resilience**
- Failure Counter fuer evcc-Verbindung: eskaliert WARNING → ERROR nach 3 Fehlschlaegen
- `evcc_reachable` Flag fuer Dashboard-Statusanzeige

### Feature (Phase 20)

**`/status` API um Arbitrage-Daten erweitert**
- Neues `battery_to_ev` Feld: active, available_kwh, ev_need_kwh, savings_ct
- Daten sofort beim ersten Abruf verfuegbar (nicht erst nach SSE-Update)

### Architektur-Entscheidung (Phase 17)

**evcc Vehicle Polling Migration: NO-GO**
- evcc `poll.mode: always` pollt nur das dem Loadpoint zugewiesene Fahrzeug
- Bei 3 EVs auf 1 Wallbox: nur 1 bekommt SoC-Updates
- SmartLoad behaelt eigenes Cloud-Polling (KiaProvider, RenaultProvider)
- Dokumentation korrigiert: `poll.mode` gehoert zum Loadpoint, nicht zum Vehicle

### Tech Debt (Phase 20)

- DEBT-01: `rl_bootstrap_max_records` config field bereits entfernt (verifiziert)
- DEBT-02: `/departure-times` Endpoint bereits entfernt (verifiziert)
- DEBT-03: `/status` API liefert Arbitrage-Daten sofort (s.o.)

### Tests

- 101 Unit Tests bestehen, keine Regressionen

---

## v6.2.1 — Critical Vehicle Data Fixes (Phase 17.1)

### Bugfixes

**evcc API Client — Error Visibility + Retry**
- `get_state()` loggt jetzt Fehler statt sie stumm zu schlucken
- 1 automatischer Retry bei `ConnectionError` mit 2s Pause
- `_login()` loggt Auth-Fehler als Warning

**Vehicle Data Staleness Race**
- `update_from_evcc()` setzt `last_update` und `data_source` immer wenn Fahrzeug verbunden ist — auch bei SoC=None
- Behebt: Fahrzeug am Wallbox mit noch nicht synchronisiertem SoC zeigte "VERALTET" statt "verbunden"
- `freshness` Property nutzt jetzt `last_update` (konsistent mit `is_data_stale()`)

**Charge Sequencer Thread Safety**
- `threading.Lock` schützt alle `requests`-Dict Zugriffe (Lesen + Schreiben)
- Behebt: `RuntimeError: dictionary changed size during iteration` bei parallelem Telegram-Zugriff
- `_urgency_reason()` nutzt neue `departure_store.get_raw_iso()` Public API statt privater `_lock`/`_times`

**DataCollector Resilience**
- Failure Counter für evcc-Verbindung: eskaliert von WARNING → ERROR nach 3 aufeinanderfolgenden Fehlschlägen
- `evcc_reachable` Flag für Dashboard-Statusanzeige

### Tests

- 101 Unit Tests bestehen (0.40s), keine Regressionen

---

## v6.2.0 — Bugfixes: PV Forecast, evcc Coexistence, Vehicle Polling, Charge Sequencer

### Bugfixes

**PV Forecast 2x Deviation (Phase 13)**
- `filter_today_solar()` filtert evcc 48h Solar-Daten auf heute — behebt systematische 2x Abweichung
- Coverage Hours auf 24 gekappt in `PVForecaster._count_future_hours`
- Date-Filter auf Europe/Berlin Timezone, angewendet bei allen Summationspunkten

**evcc Coexistence (Phase 13)**
- Command Deduplication in `Controller.apply()` — keine redundanten evcc API-Calls bei unverändertem State
- Transition-only Deactivation in Battery Arbitrage — `_deactivate_if_active()` statt immer deaktivieren
- "Defers to evcc" Eintrag im Decision Log wenn SmartLoad während PV-Surplus idle ist

**Vehicle Data Reliability (Phase 14)**
- `poll_vehicle()` merged via `update_from_api()` statt VehicleData-Objekt zu ersetzen
- Unified `is_data_stale()` mit Wallbox-Awareness (evcc/live data_source Check)
- Ad-hoc Wallbox Stale Check aus server.py entfernt, unified in `is_data_stale()`
- ManualSoC `clear()` Methode + timestamp-aware auto-clear (`poll_time > manual_ts`)

**Charge Sequencer Transition (Phase 15)**
- Current-Hour-First Slot Assignment für Top-Priority Vehicle — sofortige Transition statt Delay
- Transition Logging mit beiden Fahrzeugnamen bei Queue-Handoff
- Tariff Gap Handling mit Median-Price Synthese

**Departure Store Bugfix (Phase 16)**
- `departure_store.get_departure()` → `.get()` — behebt AttributeError in main.py
- Departure Urgency erreicht jetzt korrekt den Mode Controller

### Tests

- 101 Unit Tests bestehen (0.55s), keine Regressionen
- 14 neue Tests für Phase 13 (Dedup + Transition)
- 6 neue Tests für Phase 14 (Polling + ManualSoC)
- 4 neue Tests für Phase 15 (Sequencer)
- 5 neue Tests für Phase 16 (Departure + Decision Log)

---

## v6.1.1 — Bugfix: Poll Now Button

### Bugfix

- **Poll Now Button funktioniert jetzt zuverlässig in Produktion**
  - Manueller Refresh umgeht Provider-Backoff (vorher: Button tat nichts bei Backoff-Status)
  - Manueller Refresh umgeht Wallbox-Suppression (vorher: kein Poll wenn Fahrzeug an Wallbox)
  - `force=True` an Provider: KiaProvider sendet Wake-up-Command bei manuellem Poll
  - Event-basiertes Aufwecken des Poll-Loops (sofortige Verarbeitung statt bis zu 30s Wartezeit)

---

## v6.1.0 — Vehicle Polling + evcc Lademodus-Steuerung + Batterie-Arbitrage

### Neue Features

**Vehicle SoC Polling (Phase 9)**
- KiaProvider: Persistent VehicleManager, Progressive Backoff (2h→24h Cap), RateLimitingError-Handling
- RenaultProvider: Persistent aiohttp Session + RenaultClient, 401 Retry, asyncio-Loop Reuse
- evcc-Live-Suppression: API-Poll wird übersprungen wenn Fahrzeug an Wallbox hängt (evcc liefert Live-SoC)
- Per-Vehicle `poll_interval_minutes` in vehicles.yaml überschreibt Global-Default
- `disabled: true` Flag in vehicles.yaml schließt Fahrzeug vom Polling aus
- Stale-Threshold auf 720min (12h) erhöht — 60min war zu aggressiv für API-Provider
- Telegram Bot Token Validation beim Start (getMe-Check)

**Poll Now Button & Fahrzeuge Tab (Phase 10)**
- Neuer Dashboard-Tab "Fahrzeuge" mit Vehicle Cards (SoC, Datenalter, Provider)
- "Poll Now" Button pro Fahrzeug für manuellen SoC-Abruf
- Server-seitiger Throttle: 5 Min Cooldown zwischen Polls pro Fahrzeug
- Freshness Aging: Visuelle Alterungsanzeige der SoC-Daten
- `GET /vehicles` erweitert: freshness, poll_age, data_age, last_poll, is_stale

**evcc Lademodus-Steuerung (Phase 11)**
- EvccModeController: SmartLoad setzt aktiv PV/Min+PV/Schnell je nach optimalem Plan
- Preis-Perzentil-Logik: p≤30 → "now", p30–p60 → "minpv", p>60 → "pv"
- Override-Detection: Manuelle evcc-Modus-Änderungen werden erkannt und respektiert
- Override-Lifecycle: Override gilt bis EV-Disconnect oder Ziel-SoC erreicht
- evcc-Unreachable-Detection: Warnung nach 30 Min ohne Verbindung
- Dashboard Banners: Override-Status und evcc-Erreichbarkeit
- Neuer Endpoint: `GET /mode-control`

**LP-Gated Battery Arbitrage (Phase 12)**
- Hausbatterie speist EV wenn wirtschaftlich sinnvoll (Grid-Preis > Batterie-Kosten + Marge)
- 7-Gate Logik: EV-Bedarf, LP-Autorisierung, Modus, Profitabilität, 6h-Lookahead, Floor-SoC, Mutual Exclusion
- Dynamischer Floor: max(battery_to_ev_floor_soc, DynamicBufferCalc)
- Dashboard Banner: "Batterie speist EV (spare X ct/kWh, Y kWh verfügbar)"
- 13 Unit Tests für alle Gates und Edge Cases

### Neue Konfigurationsfelder

```yaml
battery_charge_efficiency: 0.92        # Lade-Effizienz Hausbatterie
battery_discharge_efficiency: 0.92     # Entlade-Effizienz Hausbatterie
battery_to_ev_min_profit_ct: 3.0       # Min. Ersparnis für Batterie→EV (ct/kWh)
battery_to_ev_dynamic_limit: true      # Dynamisches Floor-SoC Limit
battery_to_ev_floor_soc: 20            # Min. Batterie-SoC für Batterie→EV (%)
vehicle_poll_interval_minutes: 60      # Globales Poll-Intervall (pro Fahrzeug überschreibbar)
```

### Neue API-Endpunkte

| Methode | Endpoint | Beschreibung |
|---|---|---|
| POST | `/vehicles/refresh` | Poll Now — sofortiger SoC-Abruf (5 Min Throttle) |
| GET | `/mode-control` | Lademodus-Status (Modus, Override, evcc-Erreichbarkeit) |

### 42 neue Unit Tests

- Vehicle Provider Backoff und Session-Handling
- Poll Throttle und Freshness Tracking
- Mode Controller Perzentil-Logik und Override-Lifecycle
- Battery Arbitrage 7-Gate Logik und Profitabilitätsberechnung

---

## v6.0.1 — Bugfix: RL-Learning State-Transition + Repo-Bereinigung

### Bugfix

**RL learn_from_correction() State-Parameter vertauscht**
- `learn_from_correction(state, action, reward, state)` übergab denselben State als State und Next-State
- Q-Learning konnte keine echten State-Übergänge lernen (Q[s,a] → Q[s',a'] war identisch)
- Fix: `learn_from_correction(last_state, action, reward, state)` — korrekte Transition

### Repo-Bereinigung

- Private IPs (192.168.1.x) durch generische Platzhalter ersetzt (evcc.local, influxdb.local)
- Default-Passwörter neutralisiert (leere Strings)
- `.planning/` Entwicklungsdokumentation aus öffentlichem Repo entfernt
- MIT-Lizenz hinzugefügt
- Duplizierte Dateien entfernt (Root-CHANGELOG, vehicles.yaml.example)
- DOCS.md aktualisiert: fehlende Endpoints `/forecast`, `/events`, Override-Endpoints ergänzt
- Translations (en/de) aktualisiert
- CI-Workflow entfernt (HA Supervisor baut lokal)
- Stale `claude/*` Remote-Branches gelöscht
- GitHub-Repository-Beschreibung gesetzt

---

## v6.0.0 — Predictiver LP-Planner + PV/Verbrauchs-Prognose + Config-Validierung

### Neue Features

**HorizonPlanner (LP-basierter 24h Optimizer)**
- Rolling-Horizon Linear Programming mit scipy/HiGHS
- 96-Slot (15-Min) Joint Battery+EV Dispatch — Batterie und EV werden gemeinsam optimiert
- Ersetzt statische Euro-Preislimits durch dynamische planbasierte Optimierung
- MPC-Ansatz: nur Slot-0-Entscheidung wird angewendet, LP wird jeden Zyklus neu gelöst
- HolisticOptimizer bleibt als automatischer Fallback bei LP-Fehler aktiv

**ConsumptionForecaster**
- Hour-of-day Rolling-Average (EMA) aus InfluxDB-Historie
- Tiered Bootstrap: 7d@15min + 8-30d@hourly
- Persistentes JSON-Modell unter /data/
- Correction Factor [0.5–1.5] für Echtzeit-Anpassung

**PVForecaster**
- PV-Ertragsprognose via evcc Solar Tariff API (/api/tariff/solar)
- Rolling Correction Coefficient [0.3–3.0] mit Daytime-Guard
- Stündliche Aktualisierung
- Confidence 0.0–1.0 basierend auf Datenabdeckung

**StateStore (Thread-Safe State Management)**
- RLock-geschützter Single Source of Truth
- Atomare Snapshots für Web-Server (read-only)
- SSE-Broadcast nach jedem Update (außerhalb des Locks)

**SSE Endpoint /events**
- Server-Sent Events für Live-Dashboard-Updates ohne Polling
- ThreadedHTTPServer mit Daemon-Threads
- 30s Keepalive

**Config Validation**
- ConfigValidator prüft alle Felder beim Start
- Kritische Fehler blockieren Start mit HTML-Fehlerseite auf Port 8099
- Nicht-kritische Warnungen setzen sichere Defaults

**GET /forecast Endpoint**
- 96-Slot Verbrauchs- und PV-Prognose mit Confidence, Correction-Label, Quality-Label, Price-Zones

### Architektur-Änderungen

- Web-Server ist jetzt strikt read-only (alle Reads via StateStore.snapshot())
- Main Loop schreibt über store.update() — kein direkter State-Zugriff mehr
- HorizonPlanner als primärer Optimizer, HolisticOptimizer als Fallback bei LP-Fehler
- Forecaster-Package (forecaster/) mit ConsumptionForecaster und PVForecaster
- ThreadedHTTPServer ersetzt einfachen HTTPServer (SSE-Kompatibilität)

### Neue Konfigurationsfelder

```yaml
battery_charge_power_kw: 5.0             # Max Ladeleistung Batterie in kW
battery_min_soc: 10                      # Min SoC in % (LP-Untergrenze)
battery_max_soc: 90                      # Max SoC in % (LP-Obergrenze)
feed_in_tariff_ct: 7.0                   # Einspeisevergütung ct/kWh
ev_default_energy_kwh: 60               # Default EV-Kapazität wenn unbekannt
sequencer_enabled: true                  # Charge Sequencer aktiv
sequencer_default_charge_power_kw: 11.0 # Default Ladeleistung EV
rl_bootstrap_max_records: 1000          # Max Records für RL Bootstrap
```

### Rückwärtskompatibilität

- Bestehende config.yaml-Felder bleiben kompatibel
- HolisticOptimizer bleibt als automatischer Fallback aktiv
- Alle v5 API-Endpoints unverändert

---

## v5.2.0 — Verbrauchs- und PV-Prognose (Data Foundation)

- ConsumptionForecaster: Hausverbrauch aus InfluxDB-Historie mit EMA-Modell
- PVForecaster: PV-Ertrag via evcc Solar Tariff API
- Forecaster in Main Loop integriert (15-Min Updates, stündliche PV-Aktualisierung)
- StateStore um Forecast-Felder erweitert (consumption_forecast, pv_forecast, pv_confidence, etc.)
- Dashboard: 24h Forecast-Diagramm mit SSE-Live-Updates

---

## v5.1.0 — Thread-Safe StateStore + Config Validation + Vehicle Reliability

- StateStore: Thread-safe RLock-geschützter State mit atomaren Snapshots
- SSE Push: /events Endpoint für Live-Dashboard-Updates
- ConfigValidator: Startup-Validierung mit kritisch/nicht-kritisch Klassifizierung
- HTML-Fehlerseite bei kritischen Config-Fehlern (vor Main Loop Start)
- Vehicle SoC Refresh bei Wallbox-Verbindung (Connection-Event-basiert)
- Charge Sequencer SoC-Sync im Decision Loop (sofortige Übergabe)
- RL Bootstrap mit Record-Cap (rl_bootstrap_max_records) und Progress-Logging
- RL Bootstrap Price-Field Fix (korrekte ct->EUR Konversion)

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

## v5.0.1 — Bugfixes: Module · SystemState · InfluxDB · DriverManager

### Fixed
- **`No module named 'yaml'`** — `pyyaml` zu pip-Dependencies im Dockerfile hinzugefügt
- **`SystemState() missing 'ev_power'`** — Pflichtfeld im DataCollector-Konstruktor ergänzt (`ev_power=0.0`)
- **`InfluxDBClient has no attribute 'get_history_hours'`** — Methode `get_history_hours()` in `influxdb_client.py` implementiert
- **`DriverManager.to_api_list()`** — Methode fehlte, wird von `web/server.py` unter `/drivers` aufgerufen

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
