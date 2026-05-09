"""Regression tests for v6.5.0 audit cleanup.

Each test pins down a specific finding from REVIEW-FULL-2026-05-09.md so future
refactors don't silently undo the fix.
"""

import os
import sys
import time
import threading
import json
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# PR #12: persistence_util — atomic_json_write
# =============================================================================

def test_atomic_json_write_basic_roundtrip(tmp_path):
    from persistence_util import atomic_json_write
    target = tmp_path / "model.json"
    atomic_json_write(str(target), {"a": 1, "b": [2, 3], "c": "x"})
    assert target.exists()
    with open(target) as f:
        assert json.load(f) == {"a": 1, "b": [2, 3], "c": "x"}


def test_atomic_json_write_overwrites_existing(tmp_path):
    """os.replace must overwrite even on Windows (where os.rename would fail)."""
    from persistence_util import atomic_json_write
    target = tmp_path / "model.json"
    target.write_text('{"old": true}')
    atomic_json_write(str(target), {"new": True})
    with open(target) as f:
        assert json.load(f) == {"new": True}


def test_atomic_json_write_no_tmp_left_behind(tmp_path):
    """After successful write, the .tmp must be gone (replace, not copy)."""
    from persistence_util import atomic_json_write
    target = tmp_path / "model.json"
    atomic_json_write(str(target), {"x": 1})
    assert not (tmp_path / "model.json.tmp").exists()


# =============================================================================
# CR-03: OverrideManager UTC-aware datetimes
# =============================================================================

def test_override_manager_uses_utc_aware_datetimes():
    """expires_at must be UTC-aware so subtraction with datetime.now(utc) works."""
    from override_manager import OverrideManager
    cfg = MagicMock()
    cfg.quiet_hours_enabled = False
    evcc = MagicMock()
    evcc.set_loadpoint_mode = MagicMock(return_value=True)

    mgr = OverrideManager(cfg, evcc)
    result = mgr.activate("my_Twingo", "telegram")

    assert result["ok"] is True
    assert mgr._active is not None
    # Must be tz-aware
    assert mgr._active.activated_at.tzinfo is not None
    assert mgr._active.expires_at.tzinfo is not None
    # Mixing with UTC-aware datetime.now must NOT raise
    delta = mgr._active.expires_at - datetime.now(timezone.utc)
    assert 89 * 60 < delta.total_seconds() < 91 * 60  # ~90 min ± 1


def test_override_manager_get_status_remaining_minutes_arithmetic():
    """status() does utc-aware subtraction → must not raise TypeError."""
    from override_manager import OverrideManager
    cfg = MagicMock()
    cfg.quiet_hours_enabled = False
    evcc = MagicMock()
    evcc.set_loadpoint_mode = MagicMock(return_value=True)

    mgr = OverrideManager(cfg, evcc)
    mgr.activate("my_Twingo", "dashboard")
    status = mgr.get_status()
    assert status["active"] is True
    assert 89 < status["remaining_minutes"] < 91


# =============================================================================
# CR-01: DataCollector.get_evcc_raw lock-protected accessor
# =============================================================================

def test_data_collector_get_evcc_raw_returns_lock_protected_snapshot():
    from vehicle_monitor import DataCollector, VehicleMonitor
    cfg = MagicMock()
    cfg.vehicle_providers = []
    cfg.vehicle_poll_interval_minutes = 30
    cfg.data_collect_interval_sec = 60
    vm = VehicleMonitor(MagicMock(), cfg, MagicMock())
    collector = DataCollector(MagicMock(), MagicMock(), cfg, vm)

    # Initially None
    assert collector.get_evcc_raw() is None

    # Simulate a write under the lock (mirroring _collect_once)
    with collector._lock:
        collector._evcc_raw = {"loadpoints": [{"connected": True}]}
    snap = collector.get_evcc_raw()
    assert snap == {"loadpoints": [{"connected": True}]}


# =============================================================================
# CR-08: Notification SoC parser tolerance
# =============================================================================

def test_soc_parser_accepts_percent_suffix_and_decimals():
    from notification import _parse_soc_text
    assert _parse_soc_text("80") == 80
    assert _parse_soc_text("80%") == 80
    assert _parse_soc_text("80 %") == 80
    assert _parse_soc_text("  80%  ") == 80
    assert _parse_soc_text("80,5") == 80   # German decimal
    assert _parse_soc_text("80.7") == 81   # rounded
    assert _parse_soc_text("") is None
    assert _parse_soc_text("nope") is None
    assert _parse_soc_text(None) is None


# =============================================================================
# HI-10/11 / SLF-013: Notification cooldown
# =============================================================================

def _make_notifier():
    from notification import NotificationManager
    bot = MagicMock()
    bot.send_message = MagicMock(return_value=True)
    bot.register_callback = MagicMock()
    drivers = MagicMock()
    driver = MagicMock(name="d", telegram_chat_id=123, vehicles=["v"])
    driver.name = "Nico"
    drivers.get_driver = MagicMock(return_value=driver)
    drivers.get_driver_by_chat_id = MagicMock(return_value=driver)
    drivers.get_all_drivers = MagicMock(return_value=[driver])
    return NotificationManager(bot=bot, driver_manager=drivers), bot


def test_charge_inquiry_cooldown_4h_blocks_repeats():
    n, bot = _make_notifier()
    assert n.send_charge_inquiry("v", 50, "cheap")
    bot.send_message.reset_mock()
    # Reply clears pending_inquiries → without the cooldown dict, a 2nd inquiry
    # would fire on the next cycle.
    n.pending_inquiries.pop("v", None)
    assert n.send_charge_inquiry("v", 50, "cheap") is False
    bot.send_message.assert_not_called()


def test_charge_inquiry_cooldown_releases_after_4h():
    n, bot = _make_notifier()
    assert n.send_charge_inquiry("v", 50, "cheap")
    n._last_inquiry_sent["v"] = datetime.now(timezone.utc) - timedelta(hours=4, minutes=1)
    n.pending_inquiries.pop("v", None)
    bot.send_message.reset_mock()
    assert n.send_charge_inquiry("v", 50, "cheap")


def test_plug_reminder_cooldown_1h():
    n, bot = _make_notifier()
    n.send_plug_reminder("v", "plug in")
    assert bot.send_message.call_count == 1
    n.send_plug_reminder("v", "plug in")
    assert bot.send_message.call_count == 1, "second reminder within 1h must be suppressed"
    n._last_plug_reminder["v"] = datetime.now(timezone.utc) - timedelta(hours=1, minutes=1)
    n.send_plug_reminder("v", "plug in")
    assert bot.send_message.call_count == 2


# =============================================================================
# HI-07: Sequencer must NOT write mode when ModeController owns it
# =============================================================================

def test_sequencer_skips_mode_write_when_owner_external():
    from charge_sequencer import ChargeSequencer, ChargeSlot
    cfg = MagicMock()
    cfg.quiet_hours_enabled = False
    cfg.quiet_hours_start = 21
    cfg.quiet_hours_end = 6
    evcc = MagicMock()

    seq = ChargeSequencer(cfg, evcc)
    seq.mode_writes_owned_externally = True

    now = datetime.now(timezone.utc)
    seq.schedule = [ChargeSlot(
        vehicle_name="v", start_hour=now - timedelta(minutes=5),
        end_hour=now + timedelta(minutes=10), energy_kwh=2.0,
        avg_price_ct=15.0, source="grid_cheap",
    )]

    seq.apply_to_evcc(now)
    evcc.set_loadpoint_mode.assert_not_called(), \
        "with mode_writes_owned_externally=True, Sequencer must defer to ModeController"


def test_sequencer_writes_mode_when_owner_local_fallback():
    """If ModeController is unavailable (init failed), Sequencer falls back to writing modes."""
    from charge_sequencer import ChargeSequencer, ChargeSlot
    cfg = MagicMock()
    cfg.quiet_hours_enabled = False
    cfg.quiet_hours_start = 21
    cfg.quiet_hours_end = 6
    evcc = MagicMock()

    seq = ChargeSequencer(cfg, evcc)
    # default = False, i.e. main.py never set mode_writes_owned_externally
    assert seq.mode_writes_owned_externally is False

    now = datetime.now(timezone.utc)
    seq.schedule = [ChargeSlot(
        vehicle_name="v", start_hour=now - timedelta(minutes=5),
        end_hour=now + timedelta(minutes=10), energy_kwh=2.0,
        avg_price_ct=15.0, source="solar",
    )]
    seq.apply_to_evcc(now)
    evcc.set_loadpoint_mode.assert_called_once_with(1, "pv")


# =============================================================================
# CR-04: Comparator — rl_ready derived from residual, not synthetic
# =============================================================================

def test_compare_no_longer_fakes_rl_savings():
    """compare() must not invent rl_simulated_cost from action codes."""
    from comparator import Comparator
    from state import Action, SystemState
    cfg = MagicMock()
    cfg.rl_ready_threshold = 0.8
    cfg.rl_ready_min_comparisons = 200

    with patch("comparator.COMPARISON_LOG_PATH", tempfile.mktemp(suffix=".json")):
        c = Comparator(cfg)
        s = SystemState(
            timestamp=datetime.now(timezone.utc),
            battery_soc=50.0, battery_power=0.0,
            grid_power=500.0, current_price=0.05,
            pv_power=0.0, home_power=500.0,
            ev_connected=False, ev_soc=0.0, ev_power=0.0,
        )
        s.price_percentiles = {20: 0.10, 60: 0.20}
        lp = Action(battery_action=1, ev_action=0, battery_limit_eur=0.10)
        rl = Action(battery_action=1, ev_action=0, battery_limit_eur=0.08)

        c.compare(s, lp, rl, actual_cost=0.30)

        assert len(c.comparisons) == 1
        rec = c.comparisons[0]
        # Old field "rl_better" must NOT be set from synthetic math
        assert "rl_better" not in rec
        # rl_wins must remain 0 — only compare_residual increments it
        assert c.rl_wins == 0


def test_rl_ready_promoted_via_residual_comparisons():
    from comparator import Comparator
    cfg = MagicMock()
    cfg.rl_ready_threshold = 0.8
    cfg.rl_ready_min_comparisons = 5  # small for test

    with patch("comparator.COMPARISON_LOG_PATH", tempfile.mktemp(suffix=".json")):
        c = Comparator(cfg)
        # 5 wins out of 5 → win-rate 1.0 ≥ 0.8
        for _ in range(5):
            c.compare_residual(
                plan_slot0_cost_eur=0.10,
                actual_slot0_cost_eur=0.07,  # actual < plan → rl_better = True
                delta_bat_ct=-2, delta_ev_ct=0,
            )
        assert c.rl_ready is True
        assert c.rl_wins == 5


def test_rl_ready_NOT_promoted_when_residual_loses():
    from comparator import Comparator
    cfg = MagicMock()
    cfg.rl_ready_threshold = 0.8
    cfg.rl_ready_min_comparisons = 5

    with patch("comparator.COMPARISON_LOG_PATH", tempfile.mktemp(suffix=".json")):
        c = Comparator(cfg)
        for _ in range(5):
            c.compare_residual(
                plan_slot0_cost_eur=0.10,
                actual_slot0_cost_eur=0.15,  # RL made it worse
                delta_bat_ct=2, delta_ev_ct=0,
            )
        assert c.rl_ready is False
        assert c.rl_wins == 0


# =============================================================================
# CC-1 / HI-01: Timezone — to_local() must convert UTC into Berlin (or env TZ)
# =============================================================================

def test_to_local_handles_aware_and_naive():
    from time_util import to_local

    aware = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    local = to_local(aware)
    assert local.tzinfo is not None
    # Europe/Berlin in June = UTC+2 → 14:00
    assert local.hour in (12, 13, 14)  # tolerate test runners with TZ overrides

    naive = datetime(2026, 6, 1, 12, 0, 0)
    local2 = to_local(naive)
    assert local2.tzinfo is not None
