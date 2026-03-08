"""Tests for VHCL-01: poll_vehicle() must merge into existing VehicleData."""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vehicles.base import VehicleData
from vehicles.manager import VehicleManager


def _make_manager_with_mock(name="testcar", soc_result=75.0, range_result=200.0):
    """Create VehicleManager with a mock pollable provider."""
    cfg = {"evcc_name": name, "type": "kia", "capacity_kwh": 64, "charge_power_kw": 11}
    mgr = VehicleManager([cfg])

    # Replace provider with mock
    mock_provider = MagicMock()
    mock_provider.supports_active_poll = True
    poll_result = VehicleData(name=name, soc=soc_result, range_km=range_result,
                              capacity_kwh=64, data_source="api")
    mock_provider.poll.return_value = poll_result
    mgr.providers[name] = mock_provider

    return mgr, mock_provider


def test_poll_preserves_last_poll_timestamp():
    mgr, _ = _make_manager_with_mock()
    existing = mgr.get_vehicle("testcar")
    ts = datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc)
    existing.last_poll = ts
    existing.last_successful_poll = ts

    mgr.poll_vehicle("testcar")

    updated = mgr.get_vehicle("testcar")
    # last_successful_poll should be updated by update_from_api, but last_poll
    # set before should have survived (not been lost by object replacement)
    assert updated.last_poll == ts


def test_poll_preserves_manual_soc():
    mgr, _ = _make_manager_with_mock()
    existing = mgr.get_vehicle("testcar")
    existing.manual_soc = 80.0

    mgr.poll_vehicle("testcar")

    updated = mgr.get_vehicle("testcar")
    assert updated.manual_soc == 80.0


def test_poll_preserves_wallbox_state():
    mgr, _ = _make_manager_with_mock()
    existing = mgr.get_vehicle("testcar")
    existing.connected_to_wallbox = True
    existing.charging = True

    mgr.poll_vehicle("testcar")

    updated = mgr.get_vehicle("testcar")
    assert updated.connected_to_wallbox is True
    assert updated.charging is True


def test_poll_updates_soc_and_range():
    mgr, _ = _make_manager_with_mock(soc_result=85.0, range_result=310.0)
    existing = mgr.get_vehicle("testcar")
    existing.soc = 50.0
    existing.range_km = 150.0

    mgr.poll_vehicle("testcar")

    updated = mgr.get_vehicle("testcar")
    assert updated.soc == 85.0
    assert updated.range_km == 310.0
    assert updated.data_source == "api"
    assert updated.last_update is not None


def test_poll_returns_same_object_reference():
    mgr, _ = _make_manager_with_mock()
    existing = mgr.get_vehicle("testcar")
    existing_id = id(existing)

    result = mgr.poll_vehicle("testcar")

    current = mgr.get_vehicle("testcar")
    assert id(current) == existing_id, "poll_vehicle must return same object, not replace it"
    assert id(result) == existing_id


def test_first_poll_stores_new_vehicle_data():
    mgr, mock_provider = _make_manager_with_mock()
    # Remove existing data to simulate first poll
    mgr._vehicle_data.clear()

    result = mgr.poll_vehicle("testcar")

    assert result is not None
    assert result.soc == 75.0
    assert mgr.get_vehicle("testcar") is result
