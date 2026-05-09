"""
Shared persistence helpers — v6.5.0.

Used by forecaster/dynamic_buffer/learner subsystems to avoid duplicating the
"write-to-tmp then atomic rename" pattern. Uses os.replace (atomic on POSIX
*and* Windows; os.rename is NOT atomic on Windows when the target exists).

Public:
    atomic_json_write(path, data, indent=2)
    atomic_json_write_str(path, content)
"""

import json
import os
from pathlib import Path
from typing import Any


def atomic_json_write(path: str, data: Any, indent: int = 2) -> None:
    """Write `data` to `path` as JSON atomically.

    Crash-safe on POSIX and Windows: writes to ``path + ".tmp"`` first, fsyncs,
    then ``os.replace``s the tmp into place. If anything raises before replace,
    the original file is untouched. Caller is responsible for catching errors
    and logging — this helper does not swallow exceptions.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # fsync not supported on some platforms (e.g. Windows ReFS, network
            # shares) — replace is still safe enough; just skip the durability
            # guarantee.
            pass
    os.replace(tmp, path)


def atomic_json_write_str(path: str, content: str) -> None:
    """Like atomic_json_write but caller has already serialized to a string."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)
