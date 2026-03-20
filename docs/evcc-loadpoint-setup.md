# evcc Loadpoint-Setup: 3 Fahrzeuge auf 1 Wallbox

## Loadpoint-Architektur

SmartLoad nutzt **1 Loadpoint** (Kostal Enector) mit **3 Fahrzeugen**:

| Fahrzeug  | Template       | Cloud-Provider | Cache |
|-----------|---------------|----------------|-------|
| KIA_EV9   | kia           | Kia Connect    | 30m   |
| my_Twingo | renault       | Renault ZE     | 15m   |
| ORA_03    | offline       | keiner         | -     |

## SoC-Datenquellen

**SmartLoad nutzt eigenes Cloud-Polling** (KiaProvider, RenaultProvider) fuer den SoC aller Fahrzeuge. evcc liefert den SoC nur fuer das aktuell am Loadpoint zugewiesene Fahrzeug.

| Datenquelle | Was sie liefert | Wann verfuegbar |
|-------------|-----------------|-----------------|
| SmartLoad Cloud-Polling | SoC fuer alle Fahrzeuge | Immer (unabhaengig von Wallbox) |
| evcc `loadpoints[].vehicleSoc` | SoC des zugewiesenen Fahrzeugs | Wenn Fahrzeug am LP zugewiesen |
| evcc `vehicles[].soc` | Immer `null` | Nicht nutzbar fuer SoC-Monitoring |

## evcc poll.mode (Referenz)

> **Hinweis:** `poll.mode` ist ein **Loadpoint-Setting**, kein Vehicle-Setting.
> SmartLoad nutzt dieses Setting nicht, da eigenes Cloud-Polling aktiv ist.

Falls `poll.mode: always` am Loadpoint gewuenscht ist (z.B. fuer evcc-eigene Anzeige):

```yaml
# Korrekte Syntax — unter loadpoints, NICHT unter vehicles
loadpoints:
  - title: Wallbox
    charger: enector
    soc:
      poll:
        mode: always     # charging | connected | always
        interval: 60m
      estimate: true
```

**Einschraenkung:** `poll.mode: always` pollt nur das aktuell dem Loadpoint zugewiesene Fahrzeug. Bei 3 Fahrzeugen auf 1 Loadpoint bekommt nur 1 Fahrzeug SoC-Updates.

## Vehicle-Konfiguration in evcc.yaml

```yaml
vehicles:
  - name: KIA_EV9
    type: template
    template: kia
    title: Kia EV9
    user: <kia-connect-email>
    password: <kia-connect-password>
    vin: <VIN>
    capacity: 99.8
    cache: 30m

  - name: my_Twingo
    type: template
    template: renault
    title: Renault Twingo
    user: <renault-email>
    password: <renault-password>
    vin: <VIN>
    capacity: 22
    cache: 15m

  - name: ORA_03
    type: template
    template: offline
    title: ORA 03
    capacity: 48
```

## Pruefliste nach evcc.yaml-Aenderung

1. **evcc neu starten**
   ```bash
   sudo systemctl restart evcc
   ```

2. **evcc UI pruefen** — alle 3 Fahrzeuge muessen sichtbar sein

3. **`/api/state` manuell abrufen:**
   ```bash
   curl -s http://<evcc-host>:7070/api/state | python3 -m json.tool | grep -A5 '"loadpoints"'
   ```

4. **Logs pruefen** — keine Auth-Fehler:
   ```bash
   journalctl -u evcc --since "5 minutes ago" | grep -i "error\|auth\|lock"
   ```

## Validierungsergebnis (2026-03-20)

**NO-GO fuer evcc-only Polling.** Siehe `docs/evcc-validation-report.md`.
SmartLoad behaelt eigenes Cloud-Polling fuer alle 3 Fahrzeuge bei.
