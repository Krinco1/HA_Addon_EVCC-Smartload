"""
Retrospective replay using Home Assistant's recorder/statistics.

Why this exists:
  tools/replay.py reads SmartLoad's own InfluxDB `Smartprice` measurement —
  great for SmartLoad-internal fields like battery_action / ev_action that
  HA doesn't see. But sometimes you don't need those (or InfluxDB is
  unreachable) and you just want the energy / cost retrospective from the
  same sensors HA already has.

This script pulls hourly statistics from HA's recorder for the standard evcc
sensors and computes the same energy balance + decision quality bucket
report.

Usage (host with curl + jq + python3, or any machine with HA token):

    HA_URL=http://homeassistant.local:8123  HA_TOKEN=eyJ...  \\
        python3 /app/tools/replay_ha.py --days 7

Or set HA_URL / HA_TOKEN in env. From inside the SmartLoad container:

    docker exec -e HA_URL=http://supervisor/core \\
                -e HA_TOKEN=$SUPERVISOR_TOKEN \\
                addon_evcc_smartload \\
                python /app/tools/replay_ha.py --days 7
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Default sensors. Override via --sensors if your HA names differ.
DEFAULT_SENSORS = {
    "pv_w":      "sensor.evcc_pv_power",
    "grid_w":    "sensor.evcc_grid_power",
    "battery_w": "sensor.evcc_battery_power",
    "battery_soc": "sensor.evcc_battery_soc",
    "home_w":    "sensor.evcc_home_power",
    "tariff":    "sensor.evcc_tariff_grid",
    "ev_w":      "sensor.evcc_garage_charge_power",
}


def _ha_call(url: str, token: str, path: str, params: Dict[str, str]) -> dict:
    qs = urlencode(params)
    full = f"{url.rstrip('/')}{path}?{qs}"
    req = Request(full, headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_statistics(url: str, token: str, entity_id: str, days: int) -> List[Dict]:
    """Use the /api/recorder API. Returns list of {start, mean} dicts."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    body = {
        "type": "recorder/statistics_during_period",
        "start_time": start,
        "statistic_ids": [entity_id],
        "period": "hour",
        "types": ["mean"],
    }
    # /api/services/recorder doesn't expose statistics. Fall back to /history.
    # The standard public API is /api/history/period — not statistics-aware,
    # but good enough for hourly resampling. We resample client-side.
    path = f"/api/history/period/{start}"
    params = {"filter_entity_id": entity_id,
              "minimal_response": "true",
              "no_attributes": "true"}
    data = _ha_call(url, token, path, params)
    if not data or not data[0]:
        return []
    rows = []
    for item in data[0]:
        try:
            ts_str = item.get("last_changed") or item.get("last_updated")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            state = item.get("state")
            if state in (None, "", "unknown", "unavailable"):
                continue
            rows.append({"ts": ts, "value": float(state)})
        except Exception:
            continue
    return rows


def resample_hourly(rows: List[Dict]) -> List[Tuple[datetime, float]]:
    """Bucket state changes into hourly means."""
    if not rows:
        return []
    buckets: Dict[datetime, List[float]] = {}
    for r in rows:
        h = r["ts"].replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(h, []).append(r["value"])
    out = sorted(buckets.items())
    return [(h, sum(v) / len(v)) for h, v in out]


def analyze(series: Dict[str, List[Tuple[datetime, float]]]) -> dict:
    """Same shape as tools/replay.py — but driven by HA hourly means."""
    pv = dict(series.get("pv_w", []))
    grid = dict(series.get("grid_w", []))
    battery = dict(series.get("battery_w", []))
    home = dict(series.get("home_w", []))
    tariff = dict(series.get("tariff", []))

    if not grid or not tariff:
        return {"error": "no grid/tariff data"}

    # Common time axis: hours where we have BOTH grid and tariff
    times = sorted(set(grid) & set(tariff))
    if not times:
        return {"error": "no overlapping hours between grid and tariff"}

    grid_import_kwh = 0.0
    grid_export_kwh = 0.0
    pv_kwh = 0.0
    home_kwh = 0.0
    self_consumption_kwh = 0.0
    grid_cost_eur = 0.0

    bat_charge_buckets = {"cheap": 0, "medium": 0, "expensive": 0}
    bat_discharge_buckets = {"cheap": 0, "medium": 0, "expensive": 0}

    # Use 30/60th percentile of tariff as bucket bounds (same logic as
    # SmartLoad's internal price percentiles).
    tariff_values = sorted([tariff[t] for t in times])
    p30 = tariff_values[int(len(tariff_values) * 0.3)] if tariff_values else 0
    p60 = tariff_values[int(len(tariff_values) * 0.6)] if tariff_values else 0

    for t in times:
        gw = grid[t]
        pw = pv.get(t, 0)
        hw = home.get(t, 0)
        bw = battery.get(t, 0)
        price = tariff[t]   # EUR/kWh

        # 1h sample step
        if gw > 0:
            grid_import_kwh += gw / 1000
            grid_cost_eur += (gw / 1000) * price
        else:
            grid_export_kwh += -gw / 1000

        pv_kwh += pw / 1000
        home_kwh += hw / 1000
        self_consumption_kwh += min(pw, hw) / 1000

        # Decision quality buckets
        if price <= p30:
            bucket = "cheap"
        elif price <= p60:
            bucket = "medium"
        else:
            bucket = "expensive"

        if bw > 100:           # battery charging > 100W
            bat_charge_buckets[bucket] += 1
        elif bw < -100:        # battery discharging > 100W
            bat_discharge_buckets[bucket] += 1

    return {
        "hours": len(times),
        "grid_import_kwh": round(grid_import_kwh, 1),
        "grid_export_kwh": round(grid_export_kwh, 1),
        "pv_kwh": round(pv_kwh, 1),
        "home_kwh": round(home_kwh, 1),
        "self_consumption_kwh": round(self_consumption_kwh, 1),
        "self_consumption_ratio": round(self_consumption_kwh / max(0.01, pv_kwh), 3),
        "grid_cost_eur": round(grid_cost_eur, 2),
        "tariff_p30_eur_kwh": round(p30, 4),
        "tariff_p60_eur_kwh": round(p60, 4),
        "bat_charge_buckets": bat_charge_buckets,
        "bat_discharge_buckets": bat_discharge_buckets,
    }


def render_report(stats: Dict, days: int) -> str:
    if "error" in stats:
        return f"# Replay Report (HA, {days}d)\n\n{stats['error']}\n"

    cb = stats["bat_charge_buckets"]
    db_ = stats["bat_discharge_buckets"]
    ct = max(1, sum(cb.values()))
    dt = max(1, sum(db_.values()))

    return f"""# SmartLoad Replay (HA history) — last {days}d

Window: {stats['hours']} hourly samples
Tariff buckets: P30 = {stats['tariff_p30_eur_kwh']} EUR/kWh, P60 = {stats['tariff_p60_eur_kwh']} EUR/kWh

## Energy

| Metric | kWh |
|---|---|
| Grid import | {stats['grid_import_kwh']} |
| Grid export | {stats['grid_export_kwh']} |
| PV total    | {stats['pv_kwh']} |
| House total | {stats['home_kwh']} |
| Self-consumption (min(pv, home)) | {stats['self_consumption_kwh']} |
| **Self-consumption ratio** | **{stats['self_consumption_ratio']}** |

**Grid cost (actual paid):** {stats['grid_cost_eur']} EUR

## Battery decision quality

When the battery *charged* (>100W in):

| Bucket | Hours | % |
|---|---|---|
| ≤ P30 (cheap)     | {cb['cheap']}     | {cb['cheap']/ct*100:.0f}% |
| P30–P60 (medium)  | {cb['medium']}    | {cb['medium']/ct*100:.0f}% |
| > P60 (expensive) | {cb['expensive']} | {cb['expensive']/ct*100:.0f}% |

When the battery *discharged* (>100W out):

| Bucket | Hours | % |
|---|---|---|
| ≤ P30 (cheap)     | {db_['cheap']}     | {db_['cheap']/dt*100:.0f}% |
| P30–P60 (medium)  | {db_['medium']}    | {db_['medium']/dt*100:.0f}% |
| > P60 (expensive) | {db_['expensive']} | {db_['expensive']/dt*100:.0f}% |

**Healthy:** charge ≫ cheap, discharge ≫ expensive (Spread arbitrage).
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="HA-backed retrospective replay")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", type=str, default="-")
    ap.add_argument("--ha-url", type=str, default=os.environ.get("HA_URL", ""))
    ap.add_argument("--ha-token", type=str, default=os.environ.get(
        "HA_TOKEN", os.environ.get("SUPERVISOR_TOKEN", "")))
    args = ap.parse_args()

    if not args.ha_url or not args.ha_token:
        print("ERROR: HA_URL and HA_TOKEN must be set (or use --ha-url/--ha-token).",
              file=sys.stderr)
        print("Tip: inside the add-on container, HA_URL=http://supervisor/core "
              "and HA_TOKEN=$SUPERVISOR_TOKEN already work.", file=sys.stderr)
        return 1

    series: Dict[str, List[Tuple[datetime, float]]] = {}
    for key, entity_id in DEFAULT_SENSORS.items():
        try:
            rows = fetch_statistics(args.ha_url, args.ha_token, entity_id, args.days)
            series[key] = resample_hourly(rows)
            print(f"  fetched {entity_id}: {len(rows)} state changes -> "
                  f"{len(series[key])} hourly buckets", file=sys.stderr)
        except (HTTPError, URLError) as e:
            print(f"  ERROR fetching {entity_id}: {e}", file=sys.stderr)
            series[key] = []

    stats = analyze(series)
    report = render_report(stats, args.days)
    if args.out == "-":
        print(report)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
