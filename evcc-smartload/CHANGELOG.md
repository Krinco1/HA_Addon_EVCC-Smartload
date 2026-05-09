# EVCC-Smartload Changelog

---

## v6.6.1 — Live-Hotfix nach v6.6.0 Deploy (2026-05-09)

Zwei Issues, beide direkt aus dem v6.6.0-Live-Log entdeckt:

### DynamicBufferCalc Crash bei persistiertem Log

`step()` rief `e.to_dict()` auf alle Log-Einträge, aber `_load()` füllt
`_log` aus dem JSON mit *plain dicts* — nur frisch via `step()` selbst
angefügte Einträge sind echte `BufferEvent` Instanzen. Beim ersten Cycle
nach Restart crashte das mit `'dict' object has no attribute 'to_dict'`.
Fix: defensive isinstance-Prüfung wie in `_build_model_dict` (war dort
schon korrekt). 1-Zeilen-Fix in `dynamic_buffer.py:198`.

**Pre-existing seit Phase 5**, jetzt aufgedeckt weil v6.6.0 das Component-
Health-Tracking eingeführt hat und der Fehler im Log direkt sichtbar wurde.

### scipy.optimize fehlte zur Laufzeit

`py3-scipy` apk-Paket installiert die scipy-Basis, aber `linprog` /
HiGHS-Submodul fehlt — HorizonPlanner sagt beim Init zwar
`initialized (scipy/HiGHS LP solver)` ok, aber bei jedem `plan()`-Call
crasht der Lazy-Import von `scipy.optimize.linprog` mit
`No module named 'scipy'`. Result: HolisticOptimizer-Fallback in jedem
Cycle — d.h. **kein 96-Slot LP, nur reaktiv-heuristisch**.

Dockerfile-Fix:
- `py3-numpy` zu apk-Layer hinzugefügt
- `scipy` und `numpy` zusätzlich via pip installiert (überschreibt
  apk-Stub falls nötig)
- Build-time Selbsttest: `python3 -c "from scipy.optimize import linprog"`
  failt den Build wenn der Import nicht klappt → keine stillen
  Container-Releases mehr ohne LP-Solver

**Erkannt durch:** `Component health: 25 ok, 0 failed, 2 disabled` Logging
hat zwar HorizonPlanner als "ok" gemeldet, aber der LP-Solve-Fehler erst
zur Laufzeit sichtbar wurde. Add-on health=ok wäre also überoptimistisch
gewesen — das LP-vs-Heuristic Verhalten ist jetzt kein blinder Fleck mehr.

---

## v6.6.0 — Bootstrap-Refactor + Renault-Hardening + Component-Health (2026-05-09)

Drei strukturelle Verbesserungen, +11 neue Regressionstests.

### main.py → bootstrap.py extract

- ~250 Zeilen Init-Logik aus `main.py` herausgezogen in neues
  `bootstrap.py` Modul (`Components` dataclass + `bootstrap()` function).
- `main.py` 1087 → 933 LoC. Init ist jetzt isoliert und unit-testbar.
- `wire_web()` kapselt die 18 late-bound WebServer-Attribut-Zuweisungen
  in einer einzigen Funktion.
- Decision-Loop bleibt unverändert — variable bindings am Ende der
  Init-Phase machen den Loop-Body identisch zu v6.5.0. Loop-Refactor
  folgt in v6.7.0.

### Component-Health Backend (SLF-015 / CC-3)

Acht optionale Subsysteme (HorizonPlanner, DynamicBufferCalc,
ResidualRLAgent, SeasonalLearner, ForecastReliabilityTracker,
ReactionTimingTracker, OverrideManager, DepartureTimeStore,
EvccModeController) wurden bisher mit `try/except: log; var=None`
gewickelt — Init-Fehler waren nur im Log sichtbar, das Dashboard zeigte
"alles ok". Jetzt:

- Bootstrap trackt jeden Component-Init als `ComponentHealth(name,
  status, detail)` mit `status ∈ {"ok", "failed", "disabled"}`.
- Beim Start: zusammenfassende Health-Zeile im Log
  (`Component health: 12 ok, 1 failed, 1 disabled`) plus Detail-Lines
  für jeden failed-Eintrag.
- `/health` Endpoint liefert jetzt `{status, version, components: [...],
  components_failed_count}`. `status: "degraded"` wenn ≥1 Component
  failed ist.
- `/status` Endpoint enthält `component_health` und
  `components_failed_count` Felder.
- Dashboard-Banner ist v6.7.0 Follow-up.

### Renault Provider Hardening

- **Backoff-Overflow-Guard:** `_failure_count` wird vor dem `2**n`-Shift
  geclampt (CR/audit Pitfall). Nach 1000 fehlgeschlagenen Polls landen
  wir nicht mehr in 2**1000 Sekunden Future.
- **Auth-Error-Detection robust:** Strukturierte Felder zuerst
  (`exc.status`, `exc.status_code`, `exc.error_details[].errorCode` —
  Kamereon-Codes `err.func.401`, `err.tech.401`, `err.func.403`).
  String-Match (`'401' in str(e)`) nur als letzter Fallback.
  Verhindert false-positives wo "401" in einer normalen Fehlermeldung
  vorkommt.
- **`lastEnergyDate` Awareness:** Renault-Cloud liefert die letzte
  *cloud-bekannte* SoC, nicht eine Echtzeitmessung. Bei einem 3 Tage
  geparkten Auto returnte SmartLoad bisher veraltete Daten als
  "frisch". Neue `_renault_timestamp(battery)` Funktion zieht
  `battery.timestamp` und überschreibt `vd.last_update` damit.
  Stale-Detection (`is_data_stale`) sieht jetzt das echte
  Messdatum.

### Shutdown-Hook

- `atexit`-Handler in main.py ruft `provider.close()` auf allen
  Vehicle-Providern, die einen haben (Renault). Verhindert die
  "Unclosed client session" Warnings beim Container-Stop.

### Tests

- `+11` neue Tests in `test_v6_6_0_regressions.py`. **141/141 grün.**

### Verbleibend für v6.7.0 / v2.0

- main.py Decision-Loop → `decision_loop.py` extract (löst die letzten
  600 LoC aus main.py raus)
- web/server.py 1305 LoC Route-Registry-Refactor
- Component-Health Dashboard-Banner (Frontend-Teil)
- Multi-LP-Strategie-Entscheidung (SLF-017)

---

## v6.5.0 — Strukturelle Cleanups & ehrliche Metriken (2026-05-09)

Vier strukturelle Refactors, +16 neue Regressionstests, retrospektives Replay-Tool.

### Comparator: legacy compare() ist nicht mehr eine Lüge (CR-04)

Bisher schrieb `Comparator.compare()` synthetische "RL hat 5/3/4ct gespart"
Werte aus den Action-Codes ab — sinnvoll für die alte v5-DQN-Architektur, aber
**nicht** für den ResidualRLAgent: der ändert keine `battery_action`-Werte
mehr, nur die Preisschwellen `battery_limit_eur`. Die "RL Win-Rate" auf dem
Dashboard war daher ~100% by construction und bedeutungslos.

- `compare()` zeichnet jetzt nur noch das Action-Pair für die
  Trace-View auf (`/comparisons` Endpoint), keine Fake-Wins mehr.
- `rl_wins`, `rl_total_cost`, `rl_ready` werden ausschließlich aus
  `compare_residual()` (echte slot-0 Plan-vs-Actual-Cost) abgeleitet via
  neuem `_refresh_residual_aggregate()`.
- `get_status()` exposed jetzt `residual_samples` zusätzlich zur legacy
  `comparisons`-Zahl.

### Sequencer ↔ ModeController Owner-Kontrakt (HI-07)

Bisher schrieben beide `set_loadpoint_mode(1, ...)`. ModeController las
Sequencers Schreibvorgang als manuellen User-Override und pausierte sich
permanent. Neue Regel:

- `ChargeSequencer.mode_writes_owned_externally` (default `False`).
  `main.py` setzt sie auf `True` direkt nach erfolgreichem
  `EvccModeController` Init. Sequencer schreibt dann nur noch `targetsoc`.
- ModeController bleibt Single-Writer für `mode`. Wenn Init failed, fällt
  Sequencer auf alte Semantik zurück.

### Persistence-Util (CC-8)

`persistence_util.atomic_json_write(path, data)` — `os.replace`-basiert,
crash-safe auf Linux *und* Windows (`os.rename` war auf Windows nicht
atomic). `dynamic_buffer.py`, `forecaster/consumption.py`, `forecaster/pv.py`
migriert. `state.py`, `comparator.py`, `seasonal_learner.py`,
`forecast_reliability.py`, `reaction_timing.py`, `rl_agent.py`,
`departure_store.py` haben bereits `os.replace` und werden in einer
folgenden Session konsolidiert.

### Dead Code raus

- `rl_agent._DeprecatedDQNAgent` (~207 LoC) entfernt. Old `q_table`-Files
  werden vom ResidualRLAgent.load auto-detected und reset.

### Retrospektives Replay-Tool

`tools/replay.py` — pullt InfluxDB-State über N Tage, berechnet:
- Energie-Bilanz (Grid-Import/Export, PV, Haus, Self-Consumption)
- Tatsächliche Stromkosten in EUR
- Action-Distribution (Battery + EV)
- **Decision-Quality:** Wie oft hat die Batterie aus dem Netz geladen,
  wenn der Preis im Cheap/Medium/Expensive-Bucket war? Schnelle
  Antwort auf "Macht der Planer Sinn?".

Ausführung im Container:
```
docker exec -it addon_evcc_smartload python /app/tools/replay.py --days 7
```

### Tests

- `+16` neue Tests in `test_v6_5_0_regressions.py`. **117/117 grün.**
- Pinning der oben genannten Fixes gegen Regression: SoC-Parser-
  Toleranz, Cooldown-Logik, Sequencer-Mode-Owner, Comparator
  Residual-Drive, persistence atomic write, OverrideManager UTC.

### Verbleibend für v6.6.0 / v2.0

- main.py → `bootstrap.py` + `decision_loop.py` + `learning.py` Refactor
- Multi-LP-Strategie-Entscheidung (SLF-017)
- Component-Health-Banner (SLF-015)
- Renault Hardening (SLF-014 ff.)

---

## v6.4.1 — Audit Cleanup Bundle (2026-05-09)

Sieben low-risk-Findings aus dem Architektur-Audit (`REVIEW-FULL-2026-05-09.md`)
in einem Bundle gefixt — alle ohne Verhaltensänderung im Hauptpfad.

### Concurrency

- **CR-01:** `main.py:606` las `collector._evcc_raw` ohne Lock; DataCollector
  schreibt unter Lock. Neuer `VehicleMonitor.get_evcc_raw()` Accessor.

### Timezone-Korrektheit (deckt 6.3.1-Lücke)

- **HI-01:** `decision_log.py`, `web/server.py` (3 Stellen), `charge_sequencer.py`
  (2 Stellen) und `notification.py` (2 Stellen) nutzten `dt.astimezone()` ohne
  Argument → System-TZ (UTC im Alpine-Container) statt Europe/Berlin. Alle
  durch `to_local()` aus `time_util` ersetzt. Dashboard-Zeiten zeigen jetzt
  korrekt lokale Zeit auch ohne `TZ`-Env-Var.
- **CR-03:** `OverrideManager` nutzte naives `datetime.now()`; bei Subtraktion
  von UTC-aware Timestamps gab es `TypeError`. Jetzt durchgängig
  `datetime.now(timezone.utc)`.

### Dead Code

- **HI-02:** `optimizer/event_detector.py` (57 LoC) gelöscht — zweite
  EventDetector-Klasse, die keinen Importer hatte. `optimizer/events.py`
  ist die kanonische Quelle.

### Memory-Caps

- **HI-04:** `Comparator.comparisons` (legacy) und `_residual_comparisons`
  bekommen In-Memory-Caps (1000 / 2000 Einträge). Vorher unbegrenzt
  wachsend bei langen Laufzeiten.

### User-Facing Robustheit

- **CR-08:** `_handle_text_message` SoC-Parser akzeptiert jetzt auch `"80%"`,
  `"80 %"`, `"80,5"`, `"80.5"` — vorher nur `int(text)`, alles andere wurde
  stillschweigend verworfen. Neue Helper-Funktion `_parse_soc_text`.
- **HI-10/11 (SLF-013):** Notification-Cooldown.
  - `send_charge_inquiry`: Cooldown 4h pro Fahrzeug. Vorher wurde bei jedem
    15-min-Cycle eine identische Inquiry gesendet, sobald `pending_inquiries`
    durch eine Antwort geleert wurde — bis zu 48 Telegrams in einer 12-h-
    Niedrigpreis-Phase.
  - `send_plug_reminder`: Cooldown 1h pro Fahrzeug. Vorher 4 Reminder/Stunde
    während des Pre-Quiet-Fensters.

### Audit-Trail

- Begleitend: `.planning/REVIEW-FULL-2026-05-09.md` (gsd-code-reviewer Bericht
  mit 8 CRITICAL + 14 HIGH + 17 MEDIUM Findings) und
  `.planning/ARCHITECTURE-ANALYSIS-2026-05-09.md`.
- Verbleibende v2.0-Items: PR #9 Sequencer↔ModeController-Race,
  PR #11 Comparator-Refactor (RL Win-Rate misst nichts), main.py-Refactor.

---

## v6.4.0 — KIA-Provider entfernt + Architektur-Audit (2026-05-09)

**KIA / Hyundai / Genesis Cloud-Polling final entfernt** — Bluelink-Cloud war über
alle Versionen unzuverlässig (Rate-Limit 5091, häufige Auth-Refresh-Fehler,
Library-Fragilität). User-Realität: Kia-Provider lieferte nie produktiv SoC.

### Entfernt

- `vehicles/kia_provider.py` (148 LoC) — komplett gelöscht.
- `hyundai-kia-connect-api>=3.44,<4` Python-Dependency aus Dockerfile.
- `vehicles.yaml.example` KIA-Block entfernt; `type: renault` als primäres Cloud-
  Polling-Beispiel; `type: evcc` als Default-Empfehlung für KIA/Hyundai/VW etc.
- README, DOCS, Test-Fixtures, Notification-Doc-Strings, Dashboard-API-Beispiele
  bereinigt.

### Migrations-Pfad für KIA-User

In `evcc.yaml` einen `kia`/`hyundai`-Provider mit `poll.mode: always` und
`interval: 5m` konfigurieren. In `vehicles.yaml` dann `type: evcc` setzen.
SmartLoad liest SoC dann via evcc Loadpoint-State (siehe DOCS.md).

### Verbleibende Provider

- **Renault** (`type: renault`) — einziges aktives Cloud-Polling, gehärtet in v6.3.2.
- **Custom** (`type: custom`) — lokales HTTP für ORA/eigene Endpoints.
- **evcc** (`type: evcc`) — passive Lesemaske für alle anderen Fahrzeuge.

### Architektur-Audit

Begleitend `.planning/ARCHITECTURE-ANALYSIS-2026-05-09.md` und
`.planning/REVIEW-FULL-2026-05-09.md` erzeugt — Roadmap für v2.0:
main.py-Refactor, Multi-LP-Strategie, Component-Health-Banner,
actual_cost echt berechnen, Notification-Cooldown.

### Backwards-Compat

`type: kia/hyundai/genesis` in vehicles.yaml fällt mit Warnung auf EvccProvider
zurück, statt zu crashen. Bestehende Configs bleiben funktional, aktivieren
aber kein eigenes Cloud-Polling mehr.

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
