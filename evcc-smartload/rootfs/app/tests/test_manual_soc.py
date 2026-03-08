"""Tests for DATA-01: ManualSoC race condition fix and auto-clear."""

import sys
import os
import json
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vehicles.base import VehicleData


# ── ManualSocStore tests ──


def _make_store(tmp_path):
    """Create a ManualSocStore backed by a temp file."""
    soc_file = os.path.join(tmp_path, "manual_soc.json")
    with patch("state.MANUAL_SOC_PATH", soc_file):
        from state import ManualSocStore
        store = ManualSocStore()
    store._save_path = soc_file
    # Patch MANUAL_SOC_PATH on the instance level for _save/_load
    return store, soc_file


def test_clear_removes_manual_soc(tmp_path):
    """Test 1: clear(name) removes stored manual SoC; get() returns None."""
    soc_file = os.path.join(tmp_path, "manual_soc.json")
    with patch("state.MANUAL_SOC_PATH", soc_file):
        from state import ManualSocStore
        store = ManualSocStore()
        store.set("kona", 80.0)
        assert store.get("kona") == 80.0
        store.clear("kona")
        assert store.get("kona") is None


def test_clear_nonexistent_no_error(tmp_path):
    """Test 2: clear(name) for non-existent vehicle does not raise."""
    soc_file = os.path.join(tmp_path, "manual_soc.json")
    with patch("state.MANUAL_SOC_PATH", soc_file):
        from state import ManualSocStore
        store = ManualSocStore()
        store.clear("nonexistent")  # Should not raise


def test_set_get_timestamp_roundtrip(tmp_path):
    """Test 3: set/get/get_timestamp round-trip works correctly."""
    soc_file = os.path.join(tmp_path, "manual_soc.json")
    with patch("state.MANUAL_SOC_PATH", soc_file):
        from state import ManualSocStore
        store = ManualSocStore()
        store.set("kona", 80.0)
        assert store.get("kona") == 80.0
        ts = store.get_timestamp("kona")
        assert ts is not None
        assert isinstance(ts, datetime)


def test_manual_soc_survives_poll(tmp_path):
    """Test 4: manual_soc survives poll_vehicle() (merge fix regression test)."""
    from vehicles.manager import VehicleManager
    cfg = {"evcc_name": "kona", "type": "kia", "capacity_kwh": 64, "charge_power_kw": 11}
    mgr = VehicleManager([cfg])

    mock_provider = MagicMock()
    mock_provider.supports_active_poll = True
    poll_result = VehicleData(name="kona", soc=70.0, range_km=200.0,
                              capacity_kwh=64, data_source="api")
    mock_provider.poll.return_value = poll_result
    mgr.providers["kona"] = mock_provider

    existing = mgr.get_vehicle("kona")
    existing.manual_soc = 85.0

    mgr.poll_vehicle("kona")

    updated = mgr.get_vehicle("kona")
    assert updated.manual_soc == 85.0


def test_auto_clear_when_api_newer(tmp_path):
    """Test 5: manual_soc cleared when API poll timestamp is newer than manual override."""
    soc_file = os.path.join(tmp_path, "manual_soc.json")
    with patch("state.MANUAL_SOC_PATH", soc_file):
        from state import ManualSocStore
        store = ManualSocStore()

    # Manual SoC set 2 hours ago
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    with store._lock:
        store._data["kona"] = {
            "soc": 80.0,
            "timestamp": old_time.isoformat(),
        }
        store._save()

    assert store.get("kona") == 80.0

    # Simulate: API poll succeeds NOW (newer than manual override)
    from vehicle_monitor import VehicleMonitor
    evcc = MagicMock()
    cfg = MagicMock()
    cfg.vehicle_providers = []
    cfg.vehicle_poll_interval_minutes = 30

    monitor = VehicleMonitor(evcc, cfg, store)
    poll_time = datetime.now(timezone.utc)
    monitor._maybe_clear_manual_soc("kona", poll_time)

    assert store.get("kona") is None, "Manual SoC should be cleared when API data is newer"


def test_manual_preserved_when_api_older(tmp_path):
    """Test 6: manual_soc preserved when API poll timestamp is older than manual override."""
    soc_file = os.path.join(tmp_path, "manual_soc.json")
    with patch("state.MANUAL_SOC_PATH", soc_file):
        from state import ManualSocStore
        store = ManualSocStore()

    # Manual SoC set just NOW
    store.set("kona", 80.0)

    # Simulate: API poll with timestamp from 1 hour AGO (older than manual)
    from vehicle_monitor import VehicleMonitor
    evcc = MagicMock()
    cfg = MagicMock()
    cfg.vehicle_providers = []
    cfg.vehicle_poll_interval_minutes = 30

    monitor = VehicleMonitor(evcc, cfg, store)
    old_poll_time = datetime.now(timezone.utc) - timedelta(hours=1)
    monitor._maybe_clear_manual_soc("kona", old_poll_time)

    assert store.get("kona") == 80.0, "Manual SoC should be preserved when API data is older"


def test_get_effective_soc_manual_vs_api():
    """Test 7: get_effective_soc() returns manual_soc when set, API soc when cleared."""
    vdata = VehicleData(name="kona", soc=60.0, capacity_kwh=64)

    # No manual override → API SoC
    assert vdata.get_effective_soc() == 60.0

    # Set manual override → manual SoC
    vdata.manual_soc = 80.0
    assert vdata.get_effective_soc() == 80.0

    # Clear manual override → back to API SoC
    vdata.manual_soc = None
    assert vdata.get_effective_soc() == 60.0
