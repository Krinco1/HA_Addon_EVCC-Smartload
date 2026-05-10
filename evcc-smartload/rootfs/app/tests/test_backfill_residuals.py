"""Tests for tools/backfill_residuals.py — pure functions only (no HA call)."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backfill_residuals import (  # noqa: E402
    BACKFILL_TAG,
    build_residual_samples,
    merge_into_comparator,
    resample_hourly,
)


def _h(hour_offset: int) -> datetime:
    base = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(hours=hour_offset)


def test_resample_hourly_groups_by_hour():
    rows = [
        (_h(0).replace(minute=10), 100.0),
        (_h(0).replace(minute=40), 200.0),
        (_h(1), 50.0),
    ]
    out = resample_hourly(rows)
    assert out[_h(0)] == 150.0
    assert out[_h(1)] == 50.0


def test_build_residual_samples_skips_zero_or_negative_grid():
    grid = {_h(0): 0.0, _h(1): -500.0, _h(2): 1000.0}
    tariff = {_h(0): 0.30, _h(1): 0.30, _h(2): 0.20}
    samples = build_residual_samples(grid, tariff)
    assert len(samples) == 1
    assert samples[0]["timestamp"] == _h(2).isoformat()


def test_build_residual_samples_marks_below_median_as_win():
    # Three hours: 10/30/20 ct/kWh — median = 20
    grid = {_h(0): 1000.0, _h(1): 1000.0, _h(2): 1000.0}
    tariff = {_h(0): 0.10, _h(1): 0.30, _h(2): 0.20}
    samples = build_residual_samples(grid, tariff)
    by_ts = {s["timestamp"]: s for s in samples}
    # 10ct < 20ct median → win
    assert by_ts[_h(0).isoformat()]["rl_better"] is True
    # 30ct > 20ct median → loss
    assert by_ts[_h(1).isoformat()]["rl_better"] is False
    # 20ct == median → not strictly less → loss
    assert by_ts[_h(2).isoformat()]["rl_better"] is False


def test_build_residual_samples_tags_source_backfill():
    grid = {_h(0): 1000.0}
    tariff = {_h(0): 0.20}
    samples = build_residual_samples(grid, tariff)
    assert samples[0]["source"] == BACKFILL_TAG
    assert samples[0]["delta_bat_ct"] == 0.0
    assert samples[0]["delta_ev_ct"] == 0.0


def test_merge_into_comparator_idempotent(tmp_path):
    path = str(tmp_path / "comp.json")
    samples1 = [
        {"timestamp": _h(0).isoformat(), "plan_cost_eur": 1.0,
         "actual_cost_eur": 0.5, "rl_better": True,
         "delta_bat_ct": 0, "delta_ev_ct": 0, "source": BACKFILL_TAG},
    ]
    summary1 = merge_into_comparator(samples1, path)
    assert summary1["backfill_samples"] == 1
    assert summary1["total_samples"] == 1

    # Re-run with different samples — old backfill entries must be replaced.
    samples2 = [
        {"timestamp": _h(0).isoformat(), "plan_cost_eur": 2.0,
         "actual_cost_eur": 1.0, "rl_better": True,
         "delta_bat_ct": 0, "delta_ev_ct": 0, "source": BACKFILL_TAG},
        {"timestamp": _h(1).isoformat(), "plan_cost_eur": 1.0,
         "actual_cost_eur": 1.5, "rl_better": False,
         "delta_bat_ct": 0, "delta_ev_ct": 0, "source": BACKFILL_TAG},
    ]
    summary2 = merge_into_comparator(samples2, path)
    assert summary2["backfill_samples"] == 2
    assert summary2["total_samples"] == 2  # not 3 — old backfill dropped


def test_merge_preserves_live_samples(tmp_path):
    path = str(tmp_path / "comp.json")
    # Pre-seed with a "live" sample (no source tag) and an old backfill.
    seed = {
        "version": 2,
        "comparisons": [],
        "residual_comparisons": [
            {"timestamp": _h(0).isoformat(), "plan_cost_eur": 1.0,
             "actual_cost_eur": 0.8, "rl_better": True,
             "delta_bat_ct": 0, "delta_ev_ct": 0},
            {"timestamp": _h(0).isoformat(), "plan_cost_eur": 1.0,
             "actual_cost_eur": 0.5, "rl_better": True,
             "delta_bat_ct": 0, "delta_ev_ct": 0, "source": BACKFILL_TAG},
        ],
    }
    with open(path, "w") as f:
        json.dump(seed, f)

    new_samples = [
        {"timestamp": _h(2).isoformat(), "plan_cost_eur": 1.0,
         "actual_cost_eur": 0.9, "rl_better": True,
         "delta_bat_ct": 0, "delta_ev_ct": 0, "source": BACKFILL_TAG},
    ]
    summary = merge_into_comparator(new_samples, path)
    assert summary["live_samples"] == 1     # original live entry survived
    assert summary["backfill_samples"] == 1  # only the new backfill, old one dropped
    assert summary["total_samples"] == 2
