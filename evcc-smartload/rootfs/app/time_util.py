"""Timezone helpers — resolve local time for quiet-hours / day boundaries."""

import os
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # Python < 3.9 fallback, should not happen on HA Alpine

_DEFAULT_TZ = "Europe/Berlin"


def _resolve_tz_name() -> str:
    return os.environ.get("TZ", _DEFAULT_TZ) or _DEFAULT_TZ


def local_zone():
    name = _resolve_tz_name()
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


def to_local(dt: datetime) -> datetime:
    """Convert a timezone-aware or naive datetime to the configured local zone.

    Naive datetimes are assumed to be UTC (Alpine containers run UTC by default).
    """
    z = local_zone()
    if z is None:
        return dt
    if dt.tzinfo is None:
        from datetime import timezone as _tz
        dt = dt.replace(tzinfo=_tz.utc)
    return dt.astimezone(z)


def local_hour(dt: datetime) -> int:
    return to_local(dt).hour


def local_now() -> datetime:
    from datetime import timezone as _tz
    return to_local(datetime.now(_tz.utc))
