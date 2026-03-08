"""Tests for filter_today_solar() and its integration with calc_solar_surplus_kwh."""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest

from state import filter_today_solar, calc_solar_surplus_kwh

BERLIN = ZoneInfo("Europe/Berlin")


def _make_hourly_entries(base_date, tz_suffix="Z", hours=24):
    """Generate hourly solar forecast entries for a given date.

    Returns entries with a midday bell-curve pattern (peak ~8000W at noon).
    """
    entries = []
    for h in range(hours):
        # Bell curve: peak at 12:00, zero at night
        val = max(0, 8000 * max(0, 1 - ((h - 12) / 6) ** 2))
        if tz_suffix == "Z":
            start_str = f"{base_date}T{h:02d}:00:00Z"
        else:
            start_str = f"{base_date}T{h:02d}:00:00{tz_suffix}"
        entries.append({"start": start_str, "value": val})
    return entries


def _make_48h_entries(today_str, tomorrow_str, tz_suffix="Z"):
    """Build 48h forecast: 24 entries for today + 24 for tomorrow."""
    today = _make_hourly_entries(today_str, tz_suffix)
    tomorrow = _make_hourly_entries(tomorrow_str, tz_suffix)
    return today + tomorrow


class TestFilterTodaySolar:

    def test_48h_returns_only_today(self):
        """48h data should be filtered to only today's 24 entries."""
        now = datetime(2026, 3, 8, 14, 0, 0, tzinfo=timezone.utc)
        entries = _make_48h_entries("2026-03-08", "2026-03-09")
        result = filter_today_solar(entries, now=now)
        assert len(result) == 24
        for e in result:
            assert "2026-03-08" in e["start"]

    def test_24h_only_returns_all(self):
        """24h-only data should not lose any entries."""
        now = datetime(2026, 3, 8, 14, 0, 0, tzinfo=timezone.utc)
        entries = _make_hourly_entries("2026-03-08")
        result = filter_today_solar(entries, now=now)
        assert len(result) == 24

    def test_empty_list(self):
        """Empty input returns empty output."""
        result = filter_today_solar([])
        assert result == []

    def test_midnight_utc_plus_2(self):
        """At midnight UTC+2 (22:00 UTC), local date is the next day."""
        # 2026-03-08 22:00 UTC = 2026-03-09 00:00 Berlin (CET+1 in March before DST)
        # Actually in March 8 CET is UTC+1, so 23:00 UTC = 00:00 CET March 9
        now = datetime(2026, 3, 8, 23, 0, 0, tzinfo=timezone.utc)
        # Local Berlin time: 2026-03-09 00:00 (CET = UTC+1 in early March)
        entries = _make_48h_entries("2026-03-08", "2026-03-09")
        result = filter_today_solar(entries, now=now)
        # "Today" in Berlin is March 9, so only tomorrow's entries match
        assert len(result) == 24
        for e in result:
            assert "2026-03-09" in e["start"]

    def test_handles_z_suffix(self):
        """Entries with Z suffix are parsed correctly."""
        now = datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc)
        entries = _make_48h_entries("2026-03-08", "2026-03-09", tz_suffix="Z")
        result = filter_today_solar(entries, now=now)
        assert len(result) == 24

    def test_handles_offset_format(self):
        """Entries with +02:00 offset are parsed correctly."""
        now = datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc)
        entries = _make_48h_entries("2026-03-08", "2026-03-09", tz_suffix="+01:00")
        result = filter_today_solar(entries, now=now)
        # March 8 entries with +01:00 -> local date March 8 -> matches today
        assert len(result) == 24

    def test_calc_solar_surplus_same_for_48h_and_today_only(self):
        """calc_solar_surplus_kwh with 48h data should equal today-only data."""
        today_entries = _make_hourly_entries("2026-03-08")
        all_entries = _make_48h_entries("2026-03-08", "2026-03-09")

        now = datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc)
        surplus_today = calc_solar_surplus_kwh(today_entries, home_consumption_kw=1.0)
        surplus_48h = calc_solar_surplus_kwh(all_entries, home_consumption_kw=1.0)

        # With date filtering, 48h input should produce same result as today-only
        assert abs(surplus_48h - surplus_today) < 0.1, (
            f"48h surplus ({surplus_48h:.2f}) should match today-only ({surplus_today:.2f})"
        )

    def test_midnight_edge_23h_is_today(self):
        """Entry at 23:00 local time is still 'today'."""
        now = datetime(2026, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
        # 23:00 CET = 22:00 UTC on March 8
        entries = [{"start": "2026-03-08T22:00:00Z", "value": 100}]
        result = filter_today_solar(entries, now=now)
        # 22:00 UTC = 23:00 CET = still March 8 local -> keep
        assert len(result) == 1

    def test_midnight_edge_00h_next_day_is_tomorrow(self):
        """Entry at 00:00 local next day is 'tomorrow'."""
        now = datetime(2026, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
        # 00:00 CET March 9 = 23:00 UTC March 8
        entries = [{"start": "2026-03-08T23:00:00Z", "value": 100}]
        result = filter_today_solar(entries, now=now)
        # 23:00 UTC = 00:00 CET March 9, but today is March 8 -> exclude
        assert len(result) == 0
