"""Smoke + correctness tests for tools/replay.py against synthetic InfluxDB
result rows.

Live runs against the user's real InfluxDB happen via:

    docker exec -it addon_evcc_smartload python /app/tools/replay.py --days 7

These tests pin down:
  - analyze() integrates energy correctly across irregular timestamps
  - decision-quality buckets (cheap/medium/expensive) classify by percentile
  - gap handling (>30min between rows) is skipped, not summed
  - report formatter survives edge cases (zero PV, no actions, etc.)
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from replay import analyze, render_report  # noqa: E402


def _mk_row(ts, **fields):
    """Build a row dict like InfluxDB's response format."""
    base = {
        "time": ts.isoformat(),
        "battery_soc": 50.0,
        "battery_power": 0.0,
        "pv_power": 0.0,
        "home_power": 500.0,
        "grid_power": 500.0,
        "price_ct": 25.0,
        "ev_soc": None,
        "p20_ct": 15.0,
        "p30_ct": 18.0,
        "p40_ct": 22.0,
        "p60_ct": 30.0,
        "p80_ct": 40.0,
        "battery_action": 0,
        "ev_action": 0,
    }
    base.update(fields)
    return base


def test_analyze_empty_returns_error():
    assert analyze([]) == {"error": "no rows"}


def test_energy_integration_constant_grid_import():
    """100W grid import for 1h at 0.30 EUR/kWh = 0.10 kWh = 0.030 EUR."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0 + timedelta(minutes=15 * i), grid_power=100, price_ct=30.0)
        for i in range(5)  # 0, 15, 30, 45, 60 min → 4 intervals of 15 min = 1h
    ]
    stats = analyze(rows)
    assert stats["rows"] == 5
    # 100W * 1h = 100 Wh = 0.1 kWh
    assert abs(stats["grid_import_kwh"] - 0.1) < 0.001
    # 0.1 kWh * 0.30 EUR/kWh = 0.03 EUR
    assert abs(stats["grid_cost_eur"] - 0.03) < 0.001


def test_grid_export_separated_from_import():
    """Negative grid_power = export, must NOT count as cost."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0, grid_power=-1000, price_ct=20.0),
        _mk_row(t0 + timedelta(minutes=15), grid_power=-1000, price_ct=20.0),
    ]
    stats = analyze(rows)
    # 1000W * 0.25h = 0.25 kWh export
    assert abs(stats["grid_export_kwh"] - 0.25) < 0.01
    assert stats["grid_import_kwh"] == 0
    assert stats["grid_cost_eur"] == 0


def test_self_consumption_ratio_full_pv_match():
    """When PV exactly matches house demand, self-consumption-ratio = 1.0."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0 + timedelta(minutes=15 * i), pv_power=2000, home_power=2000)
        for i in range(4)
    ]
    stats = analyze(rows)
    assert abs(stats["self_consumption_ratio"] - 1.0) < 0.01


def test_self_consumption_ratio_pv_excess():
    """PV 4kW + house 2kW → ratio = 2/4 = 0.5."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0 + timedelta(minutes=15 * i), pv_power=4000, home_power=2000)
        for i in range(4)
    ]
    stats = analyze(rows)
    assert abs(stats["self_consumption_ratio"] - 0.5) < 0.01


def test_gap_larger_than_30min_skipped():
    """A gap > 30min between samples must NOT be integrated."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0, grid_power=1000, price_ct=30.0),
        # 2h gap — should be skipped
        _mk_row(t0 + timedelta(hours=2), grid_power=1000, price_ct=30.0),
        _mk_row(t0 + timedelta(hours=2, minutes=15), grid_power=1000, price_ct=30.0),
    ]
    stats = analyze(rows)
    # Only the 15-min interval after the gap should count: 1000W * 0.25h = 0.25 kWh
    assert abs(stats["grid_import_kwh"] - 0.25) < 0.01


def test_battery_action_distribution():
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = (
        [_mk_row(t0 + timedelta(minutes=i * 15), battery_action=1) for i in range(10)]
        + [_mk_row(t0 + timedelta(hours=3, minutes=i * 15), battery_action=6) for i in range(5)]
    )
    stats = analyze(rows)
    assert stats["bat_action_hist"] == {1: 10, 6: 5}


def test_decision_quality_charge_at_cheap_price():
    """Battery charging at price ≤ P30 → 'cheap' bucket."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0 + timedelta(minutes=15 * i),
                battery_action=1,
                price_ct=10.0,        # below p30=18.0 → cheap
                p30_ct=18.0, p60_ct=30.0)
        for i in range(4)
    ]
    stats = analyze(rows)
    assert stats["bat_charge_buckets"]["cheap"] == 4
    assert stats["bat_charge_buckets"]["medium"] == 0
    assert stats["bat_charge_buckets"]["expensive"] == 0


def test_decision_quality_charge_at_expensive_price_flagged():
    """Battery charging at price > P60 → 'expensive' bucket — this is what we want
    the dashboard to surface as a problem."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0 + timedelta(minutes=15 * i),
                battery_action=1,
                price_ct=50.0,        # above p60=30.0 → expensive
                p30_ct=18.0, p60_ct=30.0)
        for i in range(3)
    ]
    stats = analyze(rows)
    assert stats["bat_charge_buckets"]["expensive"] == 3
    assert stats["bat_charge_buckets"]["cheap"] == 0


def test_decision_quality_discharge_at_expensive_is_healthy():
    """Discharge at high price → arbitrage, healthy."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0 + timedelta(minutes=15 * i),
                battery_action=6,
                price_ct=45.0,
                p30_ct=18.0, p60_ct=30.0)
        for i in range(3)
    ]
    stats = analyze(rows)
    assert stats["bat_discharge_buckets"]["expensive"] == 3


def test_render_report_does_not_crash_on_zero_actions():
    """If the system never recorded any battery_action, division-by-zero must
    not break the report (we use max(1, total))."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _mk_row(t0 + timedelta(minutes=15 * i),
                battery_action=None, ev_action=None)
        for i in range(2)
    ]
    stats = analyze(rows)
    report = render_report(stats, days=1)
    assert "SmartLoad Replay Report" in report
    assert "Energy" in report


def test_render_report_includes_key_sections():
    """Top-level smoke: a single-row trace produces a complete markdown report."""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [_mk_row(t0), _mk_row(t0 + timedelta(minutes=15))]
    report = render_report(analyze(rows), days=1)
    for marker in ("## Energy", "## Battery action distribution",
                   "## EV action distribution",
                   "## Decision quality (battery charge alignment with price)"):
        assert marker in report, f"missing section: {marker}"


def test_realistic_24h_trace_self_consumption_plausible():
    """Sanity check: a plausible spring day (4-person household)."""
    t0 = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    for slot in range(96):  # 24h * 4 slots
        ts = t0 + timedelta(minutes=15 * slot)
        hour = slot / 4

        # Simple PV sinusoid peaking at noon
        if 6 < hour < 19:
            pv = 4000 * max(0, 1 - ((hour - 12.5) / 6.5) ** 2)
        else:
            pv = 0
        # House baseload + morning + evening peaks
        home = 250 + (1500 if 6 < hour < 9 else 0) + (2000 if 18 < hour < 22 else 0)
        # Grid = home - pv (positive = import, negative = export)
        grid = home - pv

        # Spot price: cheap at night, peak evening, dip at noon
        if 1 < hour < 5:
            price = 8
        elif 11 < hour < 14:
            price = 6
        elif 17 < hour < 21:
            price = 35
        else:
            price = 22

        rows.append(_mk_row(ts, pv_power=pv, home_power=home,
                             grid_power=grid, price_ct=price,
                             p30_ct=18, p60_ct=28))

    stats = analyze(rows)
    # Sanity: span ~ 24h, > 0 PV, > 0 home, plausible self-consumption
    assert 23 < stats["span_h"] < 25
    assert stats["pv_kwh"] > 5    # ~15-20 kWh on a sunny day
    assert stats["home_kwh"] > 5
    # 4kWp / ~20kWh-day household without battery typically lands ~15-25% direct
    # self-consumption — most of midday PV peak exceeds demand and gets exported.
    assert 0.10 < stats["self_consumption_ratio"] < 0.50
    # Grid cost should be > 0 (we import in evening peak)
    assert stats["grid_cost_eur"] > 0
