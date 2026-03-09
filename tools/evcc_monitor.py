#!/usr/bin/env python3
"""
Standalone evcc vehicle polling monitor.

Polls evcc /api/state every N minutes, tracks SoC freshness
per vehicle, detects stale data and errors, writes CSV log,
and produces a PASS/FAIL summary report.

No SmartLoad dependencies — only stdlib + requests.
"""

import argparse
import csv
import io
import os
import signal
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests")
    sys.exit(1)

DEFAULT_EVCC_URL = "http://192.168.1.66:7070"
DEFAULT_POLL_INTERVAL = 300  # 5 minutes
DEFAULT_DURATION = 48  # hours
DEFAULT_VEHICLES = ["KIA_EV9", "my_Twingo"]
LOG_FILE = "evcc_monitor_log.csv"

STALE_THRESHOLD = 3  # consecutive unchanged polls before warning
MAX_STALE_MINUTES_PASS = 120  # max stale duration for PASS
MIN_SUCCESS_RATE = 0.9  # 90% for PASS


class VehicleTracker:
    def __init__(self, name: str):
        self.name = name
        self.polls = 0
        self.successes = 0
        self.errors = 0
        self.last_soc = None
        self.soc_unchanged_count = 0
        self.max_stale_minutes = 0.0
        self.stale_start = None
        self.soc_min = None
        self.soc_max = None
        self.last_connected = False

    def record_success(self, soc: int, connected: bool, ts: datetime):
        self.polls += 1
        self.successes += 1
        self.last_connected = connected

        if self.soc_min is None or soc < self.soc_min:
            self.soc_min = soc
        if self.soc_max is None or soc > self.soc_max:
            self.soc_max = soc

        soc_changed = self.last_soc is not None and soc != self.last_soc

        if self.last_soc is not None and soc == self.last_soc and not connected:
            self.soc_unchanged_count += 1
            if self.stale_start is None:
                self.stale_start = ts
        else:
            if self.stale_start is not None:
                stale_mins = (ts - self.stale_start).total_seconds() / 60
                self.max_stale_minutes = max(self.max_stale_minutes, stale_mins)
            self.soc_unchanged_count = 0
            self.stale_start = None

        self.last_soc = soc
        return soc_changed

    def record_error(self):
        self.polls += 1
        self.errors += 1

    def finalize(self, now: datetime):
        if self.stale_start is not None:
            stale_mins = (now - self.stale_start).total_seconds() / 60
            self.max_stale_minutes = max(self.max_stale_minutes, stale_mins)

    @property
    def success_rate(self) -> float:
        return self.successes / self.polls if self.polls > 0 else 0.0

    @property
    def is_stale(self) -> bool:
        return self.soc_unchanged_count >= STALE_THRESHOLD

    def verdict(self) -> str:
        if self.polls == 0:
            return "FAIL: no polls"
        reasons = []
        if self.success_rate < MIN_SUCCESS_RATE:
            reasons.append(f"success rate {self.success_rate:.0%} < {MIN_SUCCESS_RATE:.0%}")
        if self.max_stale_minutes > MAX_STALE_MINUTES_PASS:
            reasons.append(f"max stale {self.max_stale_minutes:.0f}min > {MAX_STALE_MINUTES_PASS}min")
        if reasons:
            return "FAIL: " + ", ".join(reasons)
        return "PASS"


class EvccMonitor:
    def __init__(self, evcc_url: str, vehicles: list, poll_interval: int,
                 duration_hours: float, password: str = None, log_file: str = LOG_FILE):
        self.evcc_url = evcc_url.rstrip("/")
        self.vehicle_names = vehicles
        self.poll_interval = poll_interval
        self.duration_seconds = duration_hours * 3600
        self.password = password
        self.log_file = log_file
        self.session = requests.Session()
        self.logged_in = False
        self.trackers = {name: VehicleTracker(name) for name in vehicles}
        self.start_time = None
        self.running = True

    def _login(self):
        if self.logged_in or not self.password:
            return
        try:
            r = self.session.post(
                f"{self.evcc_url}/api/auth/login",
                json={"password": self.password},
                timeout=10,
            )
            self.logged_in = r.status_code == 200
        except Exception:
            pass

    def _get_state(self) -> dict:
        self._login()
        r = self.session.get(f"{self.evcc_url}/api/state", timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("result", data)

    def _init_csv(self):
        write_header = not os.path.exists(self.log_file)
        self.csv_file = open(self.log_file, "a", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.csv_file)
        if write_header:
            self.csv_writer.writerow(["timestamp", "vehicle", "soc", "soc_changed", "connected", "status"])

    def _log_csv(self, ts: str, vehicle: str, soc, soc_changed, connected, status: str):
        self.csv_writer.writerow([ts, vehicle, soc, soc_changed, connected, status])
        self.csv_file.flush()

    def poll_once(self):
        now = datetime.now(timezone.utc)
        ts_str = now.strftime("%Y-%m-%d %H:%M:%S")

        try:
            state = self._get_state()
        except Exception as e:
            for name, tracker in self.trackers.items():
                tracker.record_error()
                status = f"error: {e}"
                self._log_csv(ts_str, name, "", "", "", status)
                print(f"{ts_str} | {name:12s} | ---  | ERROR: {e}")
            return

        vehicles_data = state.get("vehicles", {})
        loadpoints = state.get("loadpoints", [])
        lp_connected = loadpoints[0].get("connected", False) if loadpoints else False

        for name, tracker in self.trackers.items():
            vdata = vehicles_data.get(name)
            if vdata is None:
                tracker.record_error()
                self._log_csv(ts_str, name, "", "", "", "error: vehicle not found")
                print(f"{ts_str} | {name:12s} | ---  | ERROR: not in vehicles[]")
                continue

            soc = vdata.get("soc", 0)
            connected = lp_connected  # simplified: 1 loadpoint
            soc_changed = tracker.record_success(soc, connected, now)

            if tracker.is_stale and not connected:
                status = "stale"
            else:
                status = "ok"

            changed_str = "yes" if soc_changed else ("no" if tracker.last_soc is not None else "-")
            self._log_csv(ts_str, name, soc, changed_str, connected, status)

            flag = " [STALE]" if status == "stale" else ""
            print(f"{ts_str} | {name:12s} | {soc:3d}% | {status}{flag}")

    def print_summary(self):
        now = datetime.now(timezone.utc)
        elapsed = (now - self.start_time).total_seconds() if self.start_time else 0
        hours = elapsed / 3600
        minutes = elapsed / 60

        print("\n" + "=" * 60)
        print("EVCC VEHICLE POLLING MONITOR - SUMMARY REPORT")
        print("=" * 60)
        print(f"Duration:  {hours:.1f} hours ({minutes:.0f} minutes)")
        print(f"EVCC URL:  {self.evcc_url}")
        print(f"Interval:  {self.poll_interval}s ({self.poll_interval // 60}min)")
        print()

        overall_pass = True
        for name, tracker in self.trackers.items():
            tracker.finalize(now)
            verdict = tracker.verdict()
            if not verdict.startswith("PASS"):
                overall_pass = False

            soc_range = f"{tracker.soc_min}-{tracker.soc_max}%" if tracker.soc_min is not None else "n/a"
            print(f"--- {name} ---")
            print(f"  Polls:        {tracker.polls}")
            print(f"  Successes:    {tracker.successes} ({tracker.success_rate:.0%})")
            print(f"  Errors:       {tracker.errors}")
            print(f"  Max stale:    {tracker.max_stale_minutes:.0f} min")
            print(f"  SoC range:    {soc_range}")
            print(f"  Verdict:      {verdict}")
            print()

        overall = "PASS" if overall_pass else "FAIL"
        print(f"OVERALL: {overall}")
        print("=" * 60)

    def run(self):
        self._init_csv()
        self.start_time = datetime.now(timezone.utc)

        print(f"evcc Monitor started at {self.start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"Polling {self.evcc_url} every {self.poll_interval}s for {self.duration_seconds / 3600:.0f}h")
        print(f"Vehicles: {', '.join(self.vehicle_names)}")
        print(f"Log file: {self.log_file}")
        print("-" * 60)

        end_time = self.start_time.timestamp() + self.duration_seconds

        try:
            while self.running and time.time() < end_time:
                self.poll_once()
                # Sleep in small increments so signal handling is responsive
                wake_at = time.time() + self.poll_interval
                while self.running and time.time() < wake_at and time.time() < end_time:
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.print_summary()
            if hasattr(self, "csv_file"):
                self.csv_file.close()

    def stop(self):
        self.running = False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Standalone evcc vehicle polling monitor. "
                    "Polls EVCC /api/state and tracks SoC freshness per vehicle.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python evcc_monitor.py --url http://192.168.1.66:7070 --duration 48"
    )
    parser.add_argument("--url", default=DEFAULT_EVCC_URL,
                        help=f"EVCC base URL (default: {DEFAULT_EVCC_URL})")
    parser.add_argument("--interval", type=int, default=DEFAULT_POLL_INTERVAL,
                        help=f"Poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION,
                        help=f"Monitoring duration in hours (default: {DEFAULT_DURATION})")
    parser.add_argument("--vehicles", nargs="+", default=DEFAULT_VEHICLES,
                        help=f"Vehicle names to monitor (default: {' '.join(DEFAULT_VEHICLES)})")
    parser.add_argument("--password", default=None,
                        help="EVCC admin password (optional, for authenticated setups)")
    parser.add_argument("--log-file", default=LOG_FILE,
                        help=f"CSV log file path (default: {LOG_FILE})")
    return parser.parse_args()


def main():
    args = parse_args()
    monitor = EvccMonitor(
        evcc_url=args.url,
        vehicles=args.vehicles,
        poll_interval=args.interval,
        duration_hours=args.duration,
        password=args.password,
        log_file=args.log_file,
    )

    def handle_signal(sig, frame):
        print(f"\nSignal {sig} received, stopping...")
        monitor.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    monitor.run()


if __name__ == "__main__":
    main()
