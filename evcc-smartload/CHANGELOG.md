# Changelog

## v4.2.0 (2026-02-15)

### 🏠 HA Addon Guidelines Compliance

**config.yaml `map` korrigiert:**
- Alte Syntax `config:rw` durch neue List-Syntax ersetzt
- `addon_config` (read\_only: false) statt veraltetes `config` — Addon bekommt eigenes Config-Verzeichnis
- Pfad im Container bleibt `/config/`, aber auf dem Host liegt es unter `/addon_configs/{repo}_evcc_smartload/`
- User findet `vehicles.yaml` im HA File Editor unter dem Addon-Config-Ordner

**Pfad-Verifizierung nach HA Developer Docs:**
- `/data/` — persistenter Storage (State, RL-Modell, SoC) ✅
- `/data/options.json` — Addon-Optionen aus der UI ✅
- `/config/` — `addon_config` Mount für `vehicles.yaml` ✅

---

## v4.1.1 (2026-02-15)

### 📁 vehicles.yaml automatische Bereitstellung

- `vehicles.yaml.example` wird beim ersten Start automatisch nach `/config/vehicles.yaml` kopiert
- User findet die Datei sofort im HA File Editor — kein manuelles Kopieren nötig
- Dockerfile: `vehicles.yaml.example` wird ins Image aufgenommen
- Bugfix: `CHANGELOG_v4.0.0.md` Referenz in server.py korrigiert → `CHANGELOG.md`

---

## v4.1.0 (2026-02-15)

### 🔧 HA Addon Struktur & evcc-kompatible Fahrzeug-Config

**HA Addon Struktur korrigiert:**
- `build.yaml` hinzugefügt — Multi-Arch Base Images (aarch64, amd64, armv7)
- `services.d/` entfernt — bei `init: false` wird s6-overlay nicht genutzt
- `CMD` in Dockerfile ergänzt — ohne CMD startete der Container nicht
- Dockerfile: `COPY rootfs/app /app` statt `COPY rootfs /` (nur App-Code)
- `map: config:rw` in config.yaml — Zugriff auf HA Config-Verzeichnis
- Repo-level `README.md` hinzugefügt — nötig für HA Addon Store Anzeige

**Fahrzeug-Config evcc-kompatibel:**
- Neue `vehicles.yaml.example` im evcc-YAML-Format
- Vehicle-Config aus evcc.yaml 1:1 kopierbar nach `/config/vehicles.yaml`
- Automatisches Feld-Mapping: `name`→`evcc_name`, `template`→`type`, `capacity`→`capacity_kwh`
- Unbekannte evcc-Felder werden ignoriert — dieselbe YAML für beide Systeme
- `vehicle_providers` JSON-String aus config.yaml/Schema entfernt (war fehleranfällig)
- Vehicle-Credentials nicht mehr in Addon-UI, sondern in separater YAML-Datei

**Slug-Änderung:**
- `evcc_smartload` statt `evcc_smartload_v4` — kein Versionssuffix im Slug

---

## v4.0.0 (2026-02-08)

### 🏗️ Kompletter Architektur-Neuaufbau

**Breaking Changes:**
- Neuer Slug `evcc_smartload` — Add-on muss neu installiert werden
- Modulare Codebasis ersetzt monolithische `main.py`

**Neue Architektur:**
- `main.py` von 3716 auf ~120 Zeilen reduziert
- 20+ separate Module mit klarer Verantwortung
- HTML/JS komplett aus Python-Code entfernt
- JSON-API-First Dashboard mit Auto-Refresh

**Fixes:**
- ✅ Manueller SoC überlebt jetzt Neustarts (persistent in JSON)
- ✅ Dashboard-Refresh ohne Page-Reload
- ✅ Version nur noch in `version.py` (kein Hardcoding mehr)
- ✅ Keine HTML/JS in Python f-strings mehr (keine `{{`/`}}` Kollisionen)
- ✅ Thread-safe ManualSocStore mit Locking

**Features:**
- LP + Shadow RL Hybrid-Optimierung
- Pro-Device RL Control mit SQLite
- Multi-Fahrzeug-Support (KIA, Renault, Manual, Custom, evcc)
- InfluxDB-Integration mit RL-Bootstrap
- Vollständige REST-API mit 10+ Endpoints
