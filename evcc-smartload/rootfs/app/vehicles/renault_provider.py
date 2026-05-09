"""
Renault Vehicle Provider — v6.2 (Poll Now fix).

Uses renault-api library to fetch SoC from Renault/Dacia vehicles.
Persists aiohttp session and RenaultClient across polls to avoid full re-auth each time.

config.yaml example:
  vehicles:
    - name: my_Twingo
      type: renault
      username: "email@example.com"
      password: "yourpassword"
      vin: "VF1ABC..."         # optional, auto-detected if only one car
      locale: "de_DE"          # optional, default de_DE
      capacity_kwh: 22
"""

import asyncio
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

from logging_util import log
from vehicles.base import VehicleData


class RenaultProvider:
    """Polls SoC from Renault cloud API using renault-api library with persistent session."""

    def __init__(self, config: dict):
        self.evcc_name = config.get("evcc_name") or config.get("name", "renault")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.vin = config.get("vin")
        self.locale = config.get("locale", "de_DE")
        self.capacity_kwh = float(config.get("capacity_kwh", config.get("capacity", 22)))
        self.charge_power_kw = float(config.get("charge_power_kw", 7.4))
        # Persistent connection state
        self._session = None
        self._client = None
        self._vehicle_obj = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # Backoff state
        self._failure_count: int = 0
        self._backoff_until: float = 0.0
        log("info", f"RenaultProvider: {self.evcc_name} ({self.capacity_kwh} kWh)")

    def is_in_backoff(self) -> bool:
        return time.time() < self._backoff_until

    # Cap on 2**n exponent so that even after months of failed polls we
    # don't overflow into far-future timestamps. With cap_exp=5, the backoff
    # caps at 32h (then clamped to 24h below).
    _MAX_FAILURE_EXP = 5

    def record_failure(self):
        # Clamp BEFORE the shift to avoid building 2**63 when failure_count
        # accumulates over a long outage.
        self._failure_count = min(self._failure_count + 1, self._MAX_FAILURE_EXP * 4)
        exp = min(self._failure_count, self._MAX_FAILURE_EXP)
        hours = min(2 ** exp, 24)  # 2h, 4h, 8h, 16h, 24h cap
        self._backoff_until = time.time() + hours * 3600
        log("warning", f"RenaultProvider {self.evcc_name}: backoff {hours}h (failure #{self._failure_count})")

    def record_success(self):
        if self._failure_count > 0:
            log("info", f"RenaultProvider {self.evcc_name}: recovered after {self._failure_count} failures")
        self._failure_count = 0
        self._backoff_until = 0.0

    def poll(self, force: bool = False) -> Optional[VehicleData]:
        """Fetch SoC via renault-api using persistent event loop and session.

        Args:
            force: If True, re-initialize client to get fresh data (used by Poll Now).
        """
        try:
            # aiohttp.ClientSession is bound to the loop it was created in.
            # If we recreate the loop, the old session becomes unusable
            # ("attached to different loop"). Reset session + client together.
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._session = None
                self._client = None
                self._vehicle_obj = None
            if force:
                log("info", f"RenaultProvider {self.evcc_name}: force refresh — reinitializing client")
                # Close session inside the loop before dropping references.
                if self._session is not None and not self._session.closed:
                    try:
                        self._loop.run_until_complete(self._session.close())
                    except Exception:
                        pass
                self._session = None
                self._client = None
                self._vehicle_obj = None
            return self._loop.run_until_complete(self._async_poll())
        except Exception as e:
            self.record_failure()
            log("error", f"RenaultProvider {self.evcc_name} poll error: {e}\n{traceback.format_exc()}")
            # On unknown failure drop the session so next poll starts clean.
            self._client = None
            self._vehicle_obj = None
            if self._session is not None and not self._session.closed:
                try:
                    self._loop.run_until_complete(self._session.close())
                except Exception:
                    pass
            self._session = None
            return None

    async def _async_poll(self) -> Optional[VehicleData]:
        for attempt in range(2):  # max 1 retry after re-auth
            try:
                if self._client is None:
                    log("info", f"RenaultProvider {self.evcc_name}: initializing client...")
                    await self._init_client()
                    log("info", f"RenaultProvider {self.evcc_name}: client initialized")
                battery = await self._vehicle_obj.get_battery_status()
                soc = battery.batteryLevel
                if soc is None:
                    log("warning", f"RenaultProvider {self.evcc_name}: batteryLevel is None")
                    return None

                # Renault returns the *last cloud-known* SoC. If the car has
                # been parked unplugged for days, this is stale data marked
                # fresh. Use the battery.timestamp / lastEnergyDate field
                # when present so downstream staleness detection works.
                api_ts = _renault_timestamp(battery)

                v = VehicleData(
                    name=self.evcc_name,
                    capacity_kwh=self.capacity_kwh,
                    charge_power_kw=self.charge_power_kw,
                    provider_type="renault",
                )
                v.update_from_api(float(soc))
                if api_ts is not None:
                    # Override last_update with the actual measurement time —
                    # otherwise stale-detection sees cloud cache as fresh.
                    v.last_update = api_ts
                log("info", f"RenaultProvider {self.evcc_name}: SoC={soc}% (api_ts={api_ts})")
                self.record_success()
                return v
            except Exception as e:
                if _is_auth_error(e) and attempt == 0:
                    log("info", f"RenaultProvider {self.evcc_name}: auth error — re-authenticating")
                    self._client = None
                    self._vehicle_obj = None
                    continue
                raise
        return None

    async def _init_client(self):
        """Initialize persistent aiohttp session and RenaultClient."""
        from renault_api.renault_client import RenaultClient
        import aiohttp
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        self._client = RenaultClient(websession=self._session, locale=self.locale)
        await self._client.session.login(self.username, self.password)
        account_id = await self._get_account_id(self._client)
        account = await self._client.get_api_account(account_id)
        if self.vin:
            self._vehicle_obj = await account.get_api_vehicle(self.vin)
        else:
            vehicles = await account.get_vehicles()
            items = vehicles.vehicleLinks or []
            if not items:
                raise ValueError(f"No vehicles found for {self.evcc_name}")
            self._vehicle_obj = await account.get_api_vehicle(items[0].vin)

    async def _get_account_id(self, client) -> str:
        """Get the first MYRENAULT account ID."""
        person = await client.get_person()
        accounts = person.accounts or []
        for acc in accounts:
            if acc.accountType == "MYRENAULT":
                return acc.accountId
        if accounts:
            return accounts[0].accountId
        raise ValueError("No Renault account found")

    def close(self):
        """Close persistent session (called on shutdown)."""
        if self._session and not self._session.closed:
            if self._loop and not self._loop.is_closed():
                self._loop.run_until_complete(self._session.close())
        if self._loop and not self._loop.is_closed():
            self._loop.close()

    @property
    def supports_active_poll(self) -> bool:
        return bool(self.username and self.password)


# =============================================================================
# Module helpers
# =============================================================================

def _is_auth_error(exc: Exception) -> bool:
    """Robust 401 detection — checks structured fields first, falls back to
    string matching only if the library buries the code inside the message.
    """
    # 1. aiohttp.ClientResponseError.status
    status = getattr(exc, "status", None)
    if status == 401 or status == 403:
        return True
    # 2. Some libraries expose response.status_code or .code
    for attr in ("status_code", "code", "http_code"):
        v = getattr(exc, attr, None)
        if v in (401, 403):
            return True
    # 3. renault-api KamereonResponseException carries .error_details
    err_details = getattr(exc, "error_details", None)
    if err_details is not None:
        for d in err_details if isinstance(err_details, list) else [err_details]:
            code = getattr(d, "errorCode", None) or (d.get("errorCode") if isinstance(d, dict) else None)
            if code in ("err.func.401", "err.func.403", "err.tech.401"):
                return True
    # 4. Last resort: substring match — only when nothing structured is available
    msg = str(exc).lower()
    return "401" in msg or "403" in msg or "unauthorized" in msg


def _renault_timestamp(battery) -> Optional[datetime]:
    """Extract the Renault battery measurement timestamp.

    The renault-api ``KamereonVehicleBatteryStatusData`` carries a
    ``timestamp`` field (ISO 8601 with ``Z``). Returns a UTC-aware datetime
    or None if absent / unparseable.
    """
    ts = getattr(battery, "timestamp", None)
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None
