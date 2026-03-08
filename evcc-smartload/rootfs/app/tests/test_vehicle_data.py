"""Tests for VHCL-02: is_data_stale() with wallbox awareness."""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vehicles.base import VehicleData, STALE_THRESHOLD_MINUTES


def test_not_stale_when_wallbox_connected_evcc():
    old = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES + 60)
    v = VehicleData(name="car", connected_to_wallbox=True, data_source="evcc",
                    last_update=old)
    assert v.is_data_stale() is False


def test_not_stale_when_wallbox_connected_live():
    old = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES + 60)
    v = VehicleData(name="car", connected_to_wallbox=True, data_source="live",
                    last_update=old)
    assert v.is_data_stale() is False


def test_stale_when_not_connected_old_data():
    old = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES + 60)
    v = VehicleData(name="car", connected_to_wallbox=False, last_update=old,
                    data_source="api")
    assert v.is_data_stale() is True


def test_not_stale_when_manual_soc_set():
    old = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES + 60)
    v = VehicleData(name="car", manual_soc=80.0, last_update=old)
    assert v.is_data_stale() is False


def test_stale_when_wallbox_connected_but_api_source_old():
    old = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES + 60)
    v = VehicleData(name="car", connected_to_wallbox=True, data_source="api",
                    last_update=old)
    assert v.is_data_stale() is True


def test_freshness_live_consistent_with_not_stale():
    v = VehicleData(name="car", connected_to_wallbox=True, data_source="evcc",
                    last_update=datetime.now(timezone.utc),
                    last_successful_poll=datetime.now(timezone.utc))
    assert v.freshness == "live"
    assert v.is_data_stale() is False
