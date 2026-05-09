"""Vehicle config file management — used by POST /vehicles/remove (v6.6.4).

Handles atomic mutations of /config/vehicles.yaml and /config/drivers.yaml.

Caveats:
  - PyYAML round-trip discards comments. We write a `.bak` snapshot before
    the rewrite so the user can restore comments manually if desired.
  - The running VehicleManager does NOT hot-reload — caller must restart the
    add-on (or call from within init) for changes to take effect.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from logging_util import log


def _backup(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + ".bak")
    try:
        shutil.copy2(path, bak)
        return bak
    except Exception as e:
        log("warning", f"backup of {path} failed: {e}")
        return None


def remove_vehicle(name: str, vehicles_yaml: str, drivers_yaml: Optional[str] = None) -> dict:
    """Remove a vehicle by name from vehicles.yaml and (optionally) clean it
    out of every driver's `vehicles` list in drivers.yaml.

    Returns a dict describing what was changed.

    Raises FileNotFoundError if vehicles.yaml does not exist.
    """
    import yaml  # lazy import — pyyaml is in the runtime image

    vpath = Path(vehicles_yaml)
    if not vpath.exists():
        raise FileNotFoundError(f"{vehicles_yaml} not found")

    with open(vpath, "r", encoding="utf-8") as f:
        vdata = yaml.safe_load(f) or {}

    raw_vehicles: List[dict] = vdata.get("vehicles") or []
    before = len(raw_vehicles)
    name_l = name.lower()
    kept = [v for v in raw_vehicles if str(v.get("name") or v.get("evcc_name") or "").lower() != name_l]
    removed_v = before - len(kept)

    result = {
        "vehicle_removed": removed_v > 0,
        "vehicles_before": before,
        "vehicles_after": len(kept),
        "drivers_cleaned": [],
        "vehicles_yaml_backup": None,
        "drivers_yaml_backup": None,
    }

    if removed_v == 0:
        log("info", f"remove_vehicle: '{name}' not present in {vehicles_yaml} — no-op")
        return result

    # vehicles.yaml — atomic write with backup
    bak = _backup(vpath)
    if bak:
        result["vehicles_yaml_backup"] = str(bak)
    vdata["vehicles"] = kept
    tmp = str(vpath) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(vdata, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, vpath)
    log("info", f"remove_vehicle: '{name}' removed from {vehicles_yaml} ({before} → {len(kept)})")

    # drivers.yaml — strip the vehicle from every driver's list
    if drivers_yaml:
        dpath = Path(drivers_yaml)
        if dpath.exists():
            try:
                with open(dpath, "r", encoding="utf-8") as f:
                    ddata = yaml.safe_load(f) or {}
                drivers = ddata.get("drivers") or []
                cleaned = []
                for d in drivers:
                    veh = d.get("vehicles") or []
                    veh_new = [v for v in veh if str(v).lower() != name_l]
                    if len(veh_new) != len(veh):
                        cleaned.append({"driver": d.get("name"),
                                        "before": len(veh), "after": len(veh_new)})
                        d["vehicles"] = veh_new
                if cleaned:
                    bak2 = _backup(dpath)
                    if bak2:
                        result["drivers_yaml_backup"] = str(bak2)
                    ddata["drivers"] = drivers
                    tmp = str(dpath) + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        yaml.safe_dump(ddata, f, sort_keys=False, allow_unicode=True)
                    os.replace(tmp, dpath)
                    result["drivers_cleaned"] = cleaned
                    log("info", f"remove_vehicle: stripped '{name}' from {len(cleaned)} driver(s) in {drivers_yaml}")
            except Exception as e:
                log("warning", f"remove_vehicle: drivers.yaml cleanup failed ({e}) — vehicles.yaml was still updated")
                result["drivers_yaml_error"] = str(e)

    return result


def disable_vehicle(name: str, vehicles_yaml: str) -> dict:
    """Set ``disabled: true`` on a vehicle's config (non-destructive alternative
    to remove_vehicle). VehicleManager.get_pollable_names already filters out
    disabled vehicles."""
    import yaml

    vpath = Path(vehicles_yaml)
    if not vpath.exists():
        raise FileNotFoundError(f"{vehicles_yaml} not found")

    with open(vpath, "r", encoding="utf-8") as f:
        vdata = yaml.safe_load(f) or {}

    raw_vehicles: List[dict] = vdata.get("vehicles") or []
    name_l = name.lower()
    found = False
    for v in raw_vehicles:
        if str(v.get("name") or v.get("evcc_name") or "").lower() == name_l:
            v["disabled"] = True
            found = True
            break

    if not found:
        return {"vehicle_disabled": False, "reason": "not found"}

    bak = _backup(vpath)
    tmp = str(vpath) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(vdata, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, vpath)
    log("info", f"disable_vehicle: '{name}' marked disabled in {vehicles_yaml}")

    return {"vehicle_disabled": True, "vehicles_yaml_backup": str(bak) if bak else None}
