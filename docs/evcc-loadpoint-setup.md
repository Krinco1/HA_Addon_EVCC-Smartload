# evcc Loadpoint-Setup: 3 Fahrzeuge auf 1 Wallbox

## Loadpoint-Architektur

SmartLoad nutzt **1 Loadpoint** (Kostal Enector) mit **3 Fahrzeugen**:

| Fahrzeug  | Template       | Cloud-Provider | poll.mode | Cache |
|-----------|---------------|----------------|-----------|-------|
| KIA_EV9   | kia           | Kia Connect    | `always`  | 30m   |
| my_Twingo | renault       | Renault ZE     | `always`  | 15m   |
| ORA_03    | offline       | keiner         | -         | -     |

**Wichtig:** SmartLoad liest den SoC aus dem `vehicles[]`-Array in `/api/state`, **nicht** aus `loadpoints[].vehicleSoc`. Das `vehicles[]`-Array liefert SoC-Daten unabhaengig davon, ob ein Fahrzeug gerade an der Wallbox haengt. So kann SmartLoad jederzeit den aktuellen Ladestand aller Fahrzeuge kennen.

## Vehicle-Konfiguration

### KIA_EV9

- **poll.mode: always** — evcc pollt den SoC regelmaessig, auch wenn das Fahrzeug nicht an der Wallbox haengt
- **Cache: 30m** — konservativ, um Account-Locks bei Kia Connect zu vermeiden (Kia ist restriktiver als Renault)
- Kia Connect API hat Rate-Limits; 30 Minuten Cache ist ein sicherer Startwert

### my_Twingo (Renault)

- **poll.mode: always** — wie bei Kia, permanentes Polling
- **Cache: 15m** — Renault ZE API ist weniger restriktiv, daher kuerzerer Cache
- Renault hatte bisher keine Account-Lock-Probleme

### ORA_03

- **template: offline** — bleibt unveraendert
- Kein Cloud-Provider verfuegbar, SoC wird manuell eingegeben
- Wird in dieser Validierung nicht ueberwacht

## Beispiel: vehicles-Sektion in evcc.yaml

```yaml
vehicles:
  - name: KIA_EV9
    type: template
    template: kia
    title: Kia EV9
    user: <kia-connect-email>
    password: <kia-connect-password>
    vin: <VIN>
    poll:
      mode: always
    cache: 30m

  - name: my_Twingo
    type: template
    template: renault
    title: Renault Twingo
    user: <renault-email>
    password: <renault-password>
    vin: <VIN>
    poll:
      mode: always
    cache: 15m

  - name: ORA_03
    type: template
    template: offline
    title: ORA 03
```

**Hinweis:** Nur die `vehicles`-Sektion ist hier gezeigt. Die restliche evcc.yaml (site, loadpoints, meters etc.) bleibt unveraendert.

## Pruefliste vor Start

Nach Aenderung der evcc.yaml:

1. **evcc neu starten**
   ```bash
   sudo systemctl restart evcc
   ```

2. **evcc UI pruefen** — alle 3 Fahrzeuge muessen in der Weboberflaechesichtbar sein (http://<evcc-host>:7070)

3. **`/api/state` manuell abrufen** und `vehicles`-Array pruefen:
   ```bash
   curl -s http://<evcc-host>:7070/api/state | python3 -m json.tool | grep -A5 '"vehicles"'
   ```
   Erwartung: `vehicles` enthaelt Eintraege fuer `KIA_EV9`, `my_Twingo` und `ORA_03` mit jeweiligem `soc`-Wert.

4. **Logs pruefen** — keine Authentifizierungsfehler in den evcc-Logs:
   ```bash
   journalctl -u evcc --since "5 minutes ago" | grep -i "error\|auth\|lock"
   ```

5. **30 Minuten warten**, dann erneut `/api/state` pruefen — SoC-Werte sollten sich aktualisiert haben (sofern Fahrzeug nicht voll geladen und stationaer).
