"""Tests for vehicle_config_manager.py — atomic edits of vehicles.yaml /
drivers.yaml without losing data."""

import importlib
import os
import sys
from pathlib import Path

# test_battery_arbitrage.py mocks sys.modules['yaml'] = MagicMock() at import
# time which leaks into every other test that runs after it. Force-reload the
# real PyYAML before this module's tests need it.
sys.modules.pop("yaml", None)
import yaml  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vehicle_config_manager import remove_vehicle, disable_vehicle


def _write(p: Path, data: dict):
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def test_remove_vehicle_strips_named_block(tmp_path):
    vpath = tmp_path / "vehicles.yaml"
    _write(vpath, {
        "vehicles": [
            {"name": "KIA_EV9", "type": "kia", "capacity_kwh": 99.8},
            {"name": "my_Twingo", "type": "renault", "capacity_kwh": 22},
        ]
    })

    result = remove_vehicle("KIA_EV9", str(vpath))
    assert result["vehicle_removed"] is True
    assert result["vehicles_before"] == 2
    assert result["vehicles_after"] == 1

    with open(vpath) as f:
        data = yaml.safe_load(f)
    names = [v["name"] for v in data["vehicles"]]
    assert names == ["my_Twingo"]


def test_remove_vehicle_creates_backup(tmp_path):
    vpath = tmp_path / "vehicles.yaml"
    _write(vpath, {"vehicles": [{"name": "X", "type": "kia"}]})
    remove_vehicle("X", str(vpath))
    assert (tmp_path / "vehicles.yaml.bak").exists()


def test_remove_vehicle_idempotent(tmp_path):
    """Removing a vehicle that doesn't exist is a no-op, not an error."""
    vpath = tmp_path / "vehicles.yaml"
    _write(vpath, {"vehicles": [{"name": "Twingo", "type": "renault"}]})
    result = remove_vehicle("KIA_EV9", str(vpath))
    assert result["vehicle_removed"] is False
    assert result["vehicles_after"] == 1


def test_remove_vehicle_case_insensitive(tmp_path):
    vpath = tmp_path / "vehicles.yaml"
    _write(vpath, {"vehicles": [{"name": "KIA_EV9", "type": "kia"}]})
    result = remove_vehicle("kia_ev9", str(vpath))
    assert result["vehicle_removed"] is True


def test_remove_vehicle_strips_from_drivers(tmp_path):
    vpath = tmp_path / "vehicles.yaml"
    dpath = tmp_path / "drivers.yaml"
    _write(vpath, {"vehicles": [
        {"name": "KIA_EV9", "type": "kia"},
        {"name": "Twingo", "type": "renault"},
    ]})
    _write(dpath, {"drivers": [
        {"name": "Nico", "vehicles": ["KIA_EV9", "Twingo"]},
        {"name": "Other", "vehicles": ["KIA_EV9"]},
    ]})

    result = remove_vehicle("KIA_EV9", str(vpath), str(dpath))
    assert result["vehicle_removed"] is True
    assert len(result["drivers_cleaned"]) == 2

    with open(dpath) as f:
        ddata = yaml.safe_load(f)
    drivers = {d["name"]: d["vehicles"] for d in ddata["drivers"]}
    assert drivers["Nico"] == ["Twingo"]
    assert drivers["Other"] == []


def test_remove_vehicle_no_drivers_file(tmp_path):
    """Should still work when drivers.yaml is missing — only modifies vehicles.yaml."""
    vpath = tmp_path / "vehicles.yaml"
    _write(vpath, {"vehicles": [{"name": "X", "type": "kia"}]})
    result = remove_vehicle("X", str(vpath), str(tmp_path / "drivers.yaml"))
    assert result["vehicle_removed"] is True
    assert result["drivers_cleaned"] == []


def test_remove_vehicle_raises_if_yaml_missing(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        remove_vehicle("X", str(tmp_path / "nope.yaml"))


def test_disable_vehicle_sets_flag(tmp_path):
    vpath = tmp_path / "vehicles.yaml"
    _write(vpath, {"vehicles": [
        {"name": "KIA_EV9", "type": "kia", "capacity_kwh": 99.8},
        {"name": "Twingo", "type": "renault"},
    ]})

    result = disable_vehicle("KIA_EV9", str(vpath))
    assert result["vehicle_disabled"] is True

    with open(vpath) as f:
        data = yaml.safe_load(f)
    veh = {v["name"]: v for v in data["vehicles"]}
    assert veh["KIA_EV9"]["disabled"] is True
    assert "disabled" not in veh["Twingo"]


def test_disable_vehicle_not_found(tmp_path):
    vpath = tmp_path / "vehicles.yaml"
    _write(vpath, {"vehicles": [{"name": "X", "type": "renault"}]})
    result = disable_vehicle("Y", str(vpath))
    assert result["vehicle_disabled"] is False
