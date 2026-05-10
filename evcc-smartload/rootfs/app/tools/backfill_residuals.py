"""
Comparator residual backfill from HA history (v6.6.7).

Why this exists:
  After v6.5/v6.6 the Comparator switched to residual-driven win-rate, but the
  in-flight `_residual_comparisons` list only grows when the live decision loop
  successfully runs an LP plan AND records both plan_slot0_cost and
  actual_slot0_cost. Most of the past months that didn't happen — scipy was
  silently broken (pre-v6.6.0), tariff API was occasionally 404, etc. Result:
  the dashboard shows 1% win-rate on a tiny denominator, not because the system
  is bad but because it has barely accumulated honest samples.

This tool reads HA recorder history and synthesizes residual samples that
reflect *LP arbitrage quality*: did the system buy grid energy at below-median
prices, or at above-median? That's the same signal the LP planner is
optimising for, so the resulting win-rate is a meaningful baseline.

Important honesty caveats — read before using:

  - This is NOT RL training. The samples written here always have
    delta_bat_ct=0 and delta_ev_ct=0, signalling "no RL correction was applied".
    The win-rate it produces is "LP+system arbitrage quality" — which is what
    the comparator's win_rate field actually represents in the absence of
    active RL deltas.

  - The plan baseline used is `grid_kwh * median_hourly_tariff_in_window` —
    i.e. "what would the cost have been if we'd bought the same energy at the
    median price?". `rl_better = actual_cost < plan_cost` then = "did we buy
    cheaper than median?".

  - Backfill samples are tagged with `source: "backfill"` so they can be
    distinguished from live samples in audits or later cleanup.

Usage:

    HA_URL=http://homeassistant.local:8123  HA_TOKEN=eyJ... \\
        python3 /app/tools/backfill_residuals.py --days 30

    # Inside the add-on container:
    HA_URL=http://supervisor/core HA_TOKEN=$SUPERVISOR_TOKEN \\
        python3 /app/tools/backfill_residuals.py --days 30 --apply

By default the tool runs DRY: it prints the report and exits without writing
to comparator state. Pass `--apply` to actually persist the samples to
`/data/smartprice_comparison.json`.

Exit codes:
  0  ok (samples written or dry-run completed)
  1  fatal error (HA unreachable, no data, etc.)
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

# Reuse the path constants from the SmartLoad codebase so the tool can't drift.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import COMPARISON_LOG_PATH  # type: ignore
except Exception:
    COMPARISON_LOG_PATH = "/data/smartprice_comparison.json"

DEFAULT_SENSORS = {
    "grid_w":   "sensor.evcc_grid_power",
    "tariff":   "sensor.evcc_tariff_grid",
}

BACKFILL_TAG = "backfill"


def _ha_call(url: str, token: str, path: str, params: Dict[str, str]) -> dict:
    qs = urlencode(params)
    full = f"{url.rstrip('/')}{path}?{qs}"
    req = Request(full, headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_history(url: str, token: str, entity_id: str, days: int) -> List[Tuple[datetime, float]]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    path = f"/api/history/period/{start}"
    params = {"filter_entity_id": entity_id,
              "minimal_response": "true",
              "no_attributes": "true"}
    data = _ha_call(url, token, path, params)
    if not data or not data[0]:
        return []
    rows: List[Tuple[datetime, float]] = []
    for item in data[0]:
        try:
            ts_str = item.get("last_changed") or item.get("last_updated")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            state = item.get("state")
            if state in (None, "", "unknown", "unavailable"):
                continue
            rows.append((ts, float(state)))
        except Exception:
            continue
    return rows


def resample_hourly(rows: List[Tuple[datetime, float]]) -> Dict[datetime, float]:
    buckets: Dict[datetime, List[float]] = {}
    for ts, val in rows:
        h = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(h, []).append(val)
    return {h: sum(v) / len(v) for h, v in buckets.items()}


def build_residual_samples(
    grid_hourly: Dict[datetime, float],
    tariff_hourly: Dict[datetime, float],
) -> List[Dict]:
    """For each overlapping hour, produce one residual sample.

    Slot length is 1h here (not 15min like the live loop) — this is a
    backfill approximation. We treat the hour as the slot.

    Sample shape matches Comparator._residual_comparisons entries.
    """
    times = sorted(set(grid_hourly) & set(tariff_hourly))
    if not times:
        return []

    tariffs_in_window = [tariff_hourly[t] for t in times]
    median_tariff = sorted(tariffs_in_window)[len(tariffs_in_window) // 2]

    samples: List[Dict] = []
    for t in times:
        grid_w = grid_hourly[t]
        if grid_w <= 0:
            # No grid import this hour (PV self-consumption / export-only).
            # No grid energy was bought, so cost is 0 either way — skip to
            # avoid noise samples.
            continue
        grid_kwh = grid_w / 1000.0  # 1h sample
        tariff = tariff_hourly[t]
        actual_cost = grid_kwh * tariff
        plan_cost = grid_kwh * median_tariff
        samples.append({
            "timestamp": t.isoformat(),
            "plan_cost_eur": round(plan_cost, 6),
            "actual_cost_eur": round(actual_cost, 6),
            "rl_better": actual_cost < plan_cost,
            "delta_bat_ct": 0.0,
            "delta_ev_ct": 0.0,
            "source": BACKFILL_TAG,
        })
    return samples


def merge_into_comparator(samples: List[Dict], path: str) -> Dict:
    """Read the comparator JSON, drop any existing backfill entries, append
    fresh samples, recompute rl_wins / rl_total_cost, write back."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"version": 2, "comparisons": [], "residual_comparisons": []}

    existing = data.get("residual_comparisons", []) or []
    # Drop previous backfill entries — re-running the tool is idempotent.
    live = [e for e in existing if e.get("source") != BACKFILL_TAG]
    merged = live + samples
    # Sort by timestamp so the dashboard plots are chronological.
    merged.sort(key=lambda e: e.get("timestamp", ""))

    rl_wins = sum(1 for e in merged if e.get("rl_better"))
    rl_total_cost = sum(e.get("actual_cost_eur", 0.0) for e in merged)

    data["residual_comparisons"] = merged
    data["rl_wins"] = rl_wins
    data["rl_total_cost"] = rl_total_cost
    # rl_ready stays untouched — that flag belongs to the live system.

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str)
    os.replace(tmp, path)

    return {
        "live_samples": len(live),
        "backfill_samples": len(samples),
        "total_samples": len(merged),
        "rl_wins": rl_wins,
        "win_rate": rl_wins / len(merged) if merged else 0,
        "rl_total_cost_eur": round(rl_total_cost, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill Comparator residual samples from HA history")
    ap.add_argument("--days", type=int, default=30,
                    help="Number of days of HA history to backfill (default 30)")
    ap.add_argument("--apply", action="store_true",
                    help="Actually persist the samples (default: dry-run, prints summary only)")
    ap.add_argument("--path", type=str, default=COMPARISON_LOG_PATH,
                    help=f"Comparator state file (default: {COMPARISON_LOG_PATH})")
    ap.add_argument("--ha-url", type=str, default=os.environ.get("HA_URL", ""))
    ap.add_argument("--ha-token", type=str, default=os.environ.get(
        "HA_TOKEN", os.environ.get("SUPERVISOR_TOKEN", "")))
    args = ap.parse_args()

    if not args.ha_url or not args.ha_token:
        print("ERROR: HA_URL and HA_TOKEN must be set.", file=sys.stderr)
        return 1

    print(f"Fetching {args.days}d of HA history...", file=sys.stderr)
    series: Dict[str, Dict[datetime, float]] = {}
    for key, entity_id in DEFAULT_SENSORS.items():
        try:
            rows = fetch_history(args.ha_url, args.ha_token, entity_id, args.days)
            series[key] = resample_hourly(rows)
            print(f"  {entity_id}: {len(rows)} rows -> {len(series[key])} hourly buckets",
                  file=sys.stderr)
        except (HTTPError, URLError) as e:
            print(f"  ERROR fetching {entity_id}: {e}", file=sys.stderr)
            series[key] = {}

    samples = build_residual_samples(series.get("grid_w", {}), series.get("tariff", {}))
    if not samples:
        print("ERROR: no overlapping grid/tariff hours produced any samples.", file=sys.stderr)
        return 1

    rl_wins_in_backfill = sum(1 for s in samples if s["rl_better"])
    print(f"\nGenerated {len(samples)} backfill samples", file=sys.stderr)
    print(f"  rl_better (= bought below median): {rl_wins_in_backfill}/{len(samples)} "
          f"({rl_wins_in_backfill / len(samples) * 100:.1f}%)", file=sys.stderr)

    if not args.apply:
        print("\nDRY-RUN: not writing. Re-run with --apply to persist.", file=sys.stderr)
        return 0

    summary = merge_into_comparator(samples, args.path)
    print(f"\nWrote to {args.path}", file=sys.stderr)
    print(f"  live samples kept:  {summary['live_samples']}", file=sys.stderr)
    print(f"  backfill samples:   {summary['backfill_samples']}", file=sys.stderr)
    print(f"  total now:          {summary['total_samples']}", file=sys.stderr)
    print(f"  rl_wins:            {summary['rl_wins']}", file=sys.stderr)
    print(f"  win_rate:           {summary['win_rate'] * 100:.1f}%", file=sys.stderr)
    print(f"  rl_total_cost_eur:  {summary['rl_total_cost_eur']}", file=sys.stderr)
    print("\nRestart the add-on so Comparator reloads from disk.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
