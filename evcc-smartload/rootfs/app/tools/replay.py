"""
Retrospective replay tool — analyse historical InfluxDB data.

Reads the `Smartprice` measurement, computes operational analytics, and prints
a markdown report. Useful for:

  - Validating that the recorded action distribution makes sense given the
    price/PV state distribution.
  - Spotting drifts (e.g. battery charging at high price percentile).
  - Quantifying actual grid cost incurred over a recent window.
  - PV self-consumption ratio.

Run inside the running add-on container:

    docker exec -it addon_evcc_smartload python /app/tools/replay.py --days 7

Or from the host with /data/options.json mounted at the same path.

Exit codes:
  0  report written to stdout
  1  config or InfluxDB unreachable
  2  no data in window
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Make ../ importable so we can reuse the production InfluxDBClient + Config.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import requests  # noqa: E402  — local import after path adjustment


def _load_config() -> dict:
    """Load InfluxDB connection from /data/options.json or ~/.smartload-options.json."""
    for p in ("/data/options.json", os.path.expanduser("~/.smartload-options.json")):
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    raise FileNotFoundError(
        "options.json not found at /data/options.json or ~/.smartload-options.json. "
        "Run inside the add-on container, or copy the file from the HA host."
    )


def _query_influx(cfg: dict, q: str) -> List[List]:
    base = f"{'https' if cfg.get('influxdb_ssl') else 'http'}://{cfg['influxdb_host']}:{cfg['influxdb_port']}"
    auth = (cfg.get("influxdb_username"), cfg.get("influxdb_password")) if cfg.get("influxdb_username") else None
    r = requests.get(
        f"{base}/query",
        params={"db": cfg["influxdb_database"], "q": q},
        auth=auth,
        verify=False,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json().get("results", [{}])[0].get("series", [])
    if not data:
        return []
    return data[0].get("values", [])


def fetch_states(cfg: dict, days: int) -> List[Dict]:
    """Pull every Smartprice point in the last `days` at native resolution."""
    fields = (
        "time, battery_soc, battery_power, pv_power, home_power, grid_power, "
        "price_ct, ev_soc, p20_ct, p30_ct, p40_ct, p60_ct, p80_ct, "
        "battery_action, ev_action"
    )
    q = f"SELECT {fields} FROM Smartprice WHERE time > now() - {days}d"
    rows = _query_influx(cfg, q)
    if not rows:
        return []
    keys = ["time", "battery_soc", "battery_power", "pv_power", "home_power",
            "grid_power", "price_ct", "ev_soc", "p20_ct", "p30_ct", "p40_ct",
            "p60_ct", "p80_ct", "battery_action", "ev_action"]
    return [dict(zip(keys, r)) for r in rows]


def _percentile_bucket(price_ct: float, percentiles: Dict[int, float]) -> str:
    """Classify current price into bucket ≤P30, P30-P60, >P60."""
    p30 = percentiles.get(30)
    p60 = percentiles.get(60)
    if p30 is None or p60 is None:
        return "no_pct"
    if price_ct <= p30:
        return "cheap"
    if price_ct <= p60:
        return "medium"
    return "expensive"


def analyze(rows: List[Dict]) -> Dict:
    """Compute analytics from a list of state rows."""
    if not rows:
        return {"error": "no rows"}

    # Spacing between samples — InfluxDB returns native points, typically every
    # data_collect_interval_sec (default 60s). For energy integration we use
    # the actual time delta between consecutive rows, capped at 30min to avoid
    # blowing up after gaps.
    parsed_ts = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r["time"]).replace("Z", "+00:00"))
            parsed_ts.append(ts)
        except Exception:
            parsed_ts.append(None)

    n = len(rows)
    span_h = 0.0
    if parsed_ts[0] and parsed_ts[-1]:
        span_h = (parsed_ts[-1] - parsed_ts[0]).total_seconds() / 3600

    # --- Energy & cost integration ---
    grid_import_wh = 0.0
    grid_export_wh = 0.0
    pv_wh = 0.0
    home_wh = 0.0
    grid_cost_eur = 0.0
    self_consumption_wh = 0.0

    for i in range(1, n):
        if parsed_ts[i] is None or parsed_ts[i - 1] is None:
            continue
        dt_h = (parsed_ts[i] - parsed_ts[i - 1]).total_seconds() / 3600
        if dt_h <= 0 or dt_h > 0.5:
            continue  # skip gaps > 30min
        prev = rows[i - 1]
        gp = float(prev.get("grid_power") or 0)
        pp = float(prev.get("pv_power") or 0)
        hp = float(prev.get("home_power") or 0)
        price = float(prev.get("price_ct") or 0) / 100  # EUR/kWh

        if gp > 0:
            grid_import_wh += gp * dt_h
            grid_cost_eur += gp / 1000 * dt_h * price
        else:
            grid_export_wh += -gp * dt_h
        pv_wh += pp * dt_h
        home_wh += hp * dt_h
        self_consumption_wh += min(pp, hp) * dt_h

    # --- Action distribution ---
    bat_action_hist: Dict[int, int] = {}
    ev_action_hist: Dict[int, int] = {}
    for r in rows:
        ba = r.get("battery_action")
        ea = r.get("ev_action")
        if ba is not None:
            bat_action_hist[int(ba)] = bat_action_hist.get(int(ba), 0) + 1
        if ea is not None:
            ev_action_hist[int(ea)] = ev_action_hist.get(int(ea), 0) + 1

    # --- Decision quality: when did battery charge from grid? ---
    bat_charge_buckets = {"cheap": 0, "medium": 0, "expensive": 0, "no_pct": 0}
    bat_discharge_buckets = {"cheap": 0, "medium": 0, "expensive": 0, "no_pct": 0}
    for r in rows:
        ba = r.get("battery_action")
        if ba is None:
            continue
        ba = int(ba)
        price_ct = float(r.get("price_ct") or 0)
        pct = {p: float(r.get(f"p{p}_ct") or 0) / 100 for p in (30, 60)}
        # convert to EUR/kWh for bucket comparison
        price_eur = price_ct / 100
        bucket = _percentile_bucket(price_eur, pct)
        if ba in (1, 2, 3, 4):  # charge actions
            bat_charge_buckets[bucket] += 1
        elif ba == 6:  # discharge
            bat_discharge_buckets[bucket] += 1

    return {
        "rows": n,
        "span_h": round(span_h, 1),
        "grid_import_kwh": round(grid_import_wh / 1000, 2),
        "grid_export_kwh": round(grid_export_wh / 1000, 2),
        "pv_kwh": round(pv_wh / 1000, 2),
        "home_kwh": round(home_wh / 1000, 2),
        "self_consumption_kwh": round(self_consumption_wh / 1000, 2),
        "self_consumption_ratio": round(self_consumption_wh / max(1, pv_wh), 3),
        "grid_cost_eur": round(grid_cost_eur, 2),
        "bat_action_hist": bat_action_hist,
        "ev_action_hist": ev_action_hist,
        "bat_charge_buckets": bat_charge_buckets,
        "bat_discharge_buckets": bat_discharge_buckets,
    }


def render_report(stats: Dict, days: int) -> str:
    if "error" in stats:
        return f"# Replay Report — last {days}d\n\nNo data: {stats['error']}\n"

    bat_names = {0: "hold", 1: "charge≤P20", 2: "charge≤P40", 3: "charge≤P60",
                 4: "charge≤max", 5: "PV-only", 6: "discharge"}
    ev_names = {0: "off", 1: "≤P30", 2: "≤P60", 3: "≤max", 4: "PV-only"}

    bat_total = max(1, sum(stats["bat_action_hist"].values()))
    bat_lines = "\n".join(
        f"|  {k}={bat_names.get(k, '?')}  | {v} | {v/bat_total*100:.1f}% |"
        for k, v in sorted(stats["bat_action_hist"].items())
    )
    ev_total = max(1, sum(stats["ev_action_hist"].values()))
    ev_lines = "\n".join(
        f"|  {k}={ev_names.get(k, '?')}  | {v} | {v/ev_total*100:.1f}% |"
        for k, v in sorted(stats["ev_action_hist"].items())
    )

    cb = stats["bat_charge_buckets"]
    db_ = stats["bat_discharge_buckets"]
    charge_total = max(1, sum(cb.values()))
    discharge_total = max(1, sum(db_.values()))

    return f"""# SmartLoad Replay Report — last {days}d

**Window:** {stats['span_h']}h, {stats['rows']} samples

## Energy

| Metric | kWh |
|---|---|
| Grid import | {stats['grid_import_kwh']} |
| Grid export | {stats['grid_export_kwh']} |
| PV total | {stats['pv_kwh']} |
| House total | {stats['home_kwh']} |
| Self-consumption (min(pv, home)) | {stats['self_consumption_kwh']} |
| Self-consumption ratio | {stats['self_consumption_ratio']} |

**Grid cost (actual):** {stats['grid_cost_eur']} EUR

## Battery action distribution

| Action | Count | % |
|---|---|---|
{bat_lines}

## EV action distribution

| Action | Count | % |
|---|---|---|
{ev_lines}

## Decision quality (battery charge alignment with price)

When the battery *charged from grid* (actions 1-4), the price percentile bucket was:

| Bucket | Count | % |
|---|---|---|
| ≤ P30 (cheap) | {cb['cheap']} | {cb['cheap']/charge_total*100:.1f}% |
| P30–P60 (medium) | {cb['medium']} | {cb['medium']/charge_total*100:.1f}% |
| > P60 (expensive) | {cb['expensive']} | {cb['expensive']/charge_total*100:.1f}% |
| no percentile data | {cb['no_pct']} | {cb['no_pct']/charge_total*100:.1f}% |

**Healthy** if cheap >> expensive. If expensive > cheap, the planner is
charging at the wrong time → check tariff feed + price_max_ct config.

When the battery *discharged* (action 6):

| Bucket | Count | % |
|---|---|---|
| ≤ P30 (cheap) | {db_['cheap']} | {db_['cheap']/discharge_total*100:.1f}% |
| P30–P60 (medium) | {db_['medium']} | {db_['medium']/discharge_total*100:.1f}% |
| > P60 (expensive) | {db_['expensive']} | {db_['expensive']/discharge_total*100:.1f}% |
| no percentile data | {db_['no_pct']} | {db_['no_pct']/discharge_total*100:.1f}% |

**Healthy** if expensive >> cheap (discharging at expensive prices = arbitrage).
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="SmartLoad retrospective replay")
    ap.add_argument("--days", type=int, default=7, help="window size (days, default 7)")
    ap.add_argument("--out", type=str, default="-", help="report output path or '-' for stdout")
    args = ap.parse_args()

    try:
        cfg = _load_config()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not cfg.get("influxdb_host"):
        print("ERROR: influxdb_host not configured in options.json", file=sys.stderr)
        return 1

    try:
        rows = fetch_states(cfg, days=args.days)
    except Exception as e:
        print(f"ERROR: InfluxDB query failed: {e}", file=sys.stderr)
        return 1

    if not rows:
        print(f"No data in last {args.days}d", file=sys.stderr)
        return 2

    stats = analyze(rows)
    report = render_report(stats, days=args.days)

    if args.out == "-":
        print(report)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
