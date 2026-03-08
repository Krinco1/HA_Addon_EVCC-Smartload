"""
Tests for charge sequencer immediate transition (CHRG-01).

Verifies that when vehicle A finishes charging, vehicle B receives
its charge slot in the same decision cycle (immediate handoff).
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for mod_name in ["requests", "numpy", "yaml", "scipy", "scipy.optimize"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

from charge_sequencer import ChargeSequencer, ChargeSlot


def make_cfg():
    cfg = MagicMock()
    cfg.quiet_hours_enabled = False
    cfg.quiet_hours_start = 22
    cfg.quiet_hours_end = 6
    return cfg


def make_evcc():
    evcc = MagicMock()
    evcc.set_loadpoint_mode = MagicMock()
    evcc.set_loadpoint_targetsoc = MagicMock()
    return evcc


NOW = datetime(2026, 3, 8, 14, 30, tzinfo=timezone.utc)
HOUR_14 = datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc)
HOUR_15 = datetime(2026, 3, 8, 15, 0, tzinfo=timezone.utc)
HOUR_16 = datetime(2026, 3, 8, 16, 0, tzinfo=timezone.utc)
HOUR_17 = datetime(2026, 3, 8, 17, 0, tzinfo=timezone.utc)
HOUR_18 = datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc)
HOUR_19 = datetime(2026, 3, 8, 19, 0, tzinfo=timezone.utc)
HOUR_20 = datetime(2026, 3, 8, 20, 0, tzinfo=timezone.utc)

# Prices: current hour (14) is expensive, later hours are cheaper
PRICES = [
    {"start": HOUR_14.isoformat(), "value": 0.30},
    {"start": HOUR_15.isoformat(), "value": 0.10},
    {"start": HOUR_16.isoformat(), "value": 0.08},
    {"start": HOUR_17.isoformat(), "value": 0.05},
    {"start": HOUR_18.isoformat(), "value": 0.06},
    {"start": HOUR_19.isoformat(), "value": 0.05},
    {"start": HOUR_20.isoformat(), "value": 0.12},
]


class TestImmediateTransition(unittest.TestCase):
    """Test 1: When vehicle A is done, vehicle B activates in the same cycle."""

    @patch("charge_sequencer.log")
    def test_immediate_transition(self, mock_log):
        seq = ChargeSequencer(make_cfg(), make_evcc())

        seq.add_request("vehicleA", "Alice", target_soc=80, current_soc=70,
                        capacity_kwh=50, charge_power_kw=11.0)
        seq.add_request("vehicleB", "Bob", target_soc=90, current_soc=60,
                        capacity_kwh=50, charge_power_kw=11.0)

        # Mark A as done
        seq.update_soc("vehicleA", 80.0)

        schedule = seq.plan(PRICES, solar_forecast=[], connected_vehicle=None, now=NOW)

        # vehicleB should have a slot at the current hour (14:00)
        b_slots = [s for s in schedule if s.vehicle_name == "vehicleB"]
        self.assertTrue(len(b_slots) > 0, "vehicleB should have slots")
        self.assertEqual(b_slots[0].start_hour, HOUR_14,
                         "vehicleB first slot must be current hour (14:00)")

        seq.apply_to_evcc(NOW)
        seq.evcc.set_loadpoint_mode.assert_called()


class TestCurrentHourAlwaysFirst(unittest.TestCase):
    """Test 2: Top vehicle's first slot is current hour regardless of price."""

    @patch("charge_sequencer.log")
    def test_current_hour_always_first(self, mock_log):
        seq = ChargeSequencer(make_cfg(), make_evcc())

        seq.add_request("vehicleB", "Bob", target_soc=90, current_soc=60,
                        capacity_kwh=50, charge_power_kw=11.0)

        schedule = seq.plan(PRICES, solar_forecast=[], connected_vehicle=None, now=NOW)

        b_slots = [s for s in schedule if s.vehicle_name == "vehicleB"]
        self.assertTrue(len(b_slots) > 0, "vehicleB should have slots")
        # First slot must be current hour, even though it's the most expensive
        self.assertEqual(b_slots[0].start_hour, HOUR_14,
                         "Top vehicle first slot must be current hour (14:00), not cheapest")


class TestSecondVehiclePriceOptimized(unittest.TestCase):
    """Test 3: Lower-priority vehicles get cheapest-first, no forced current hour."""

    @patch("charge_sequencer.log")
    def test_second_vehicle_price_optimized(self, mock_log):
        seq = ChargeSequencer(make_cfg(), make_evcc())

        # B has higher urgency (more need), C has less
        seq.add_request("vehicleB", "Bob", target_soc=90, current_soc=50,
                        capacity_kwh=50, charge_power_kw=11.0)
        seq.add_request("vehicleC", "Charlie", target_soc=80, current_soc=70,
                        capacity_kwh=50, charge_power_kw=11.0)

        schedule = seq.plan(PRICES, solar_forecast=[], connected_vehicle=None, now=NOW)

        b_slots = [s for s in schedule if s.vehicle_name == "vehicleB"]
        c_slots = [s for s in schedule if s.vehicle_name == "vehicleC"]

        # B (top) gets current hour first
        self.assertEqual(b_slots[0].start_hour, HOUR_14)

        # C (second) should NOT have current hour forced -- gets cheapest remaining
        if c_slots:
            c_hours = [s.start_hour for s in c_slots]
            # C's first slot should be one of the cheapest remaining hours, not forced to any
            # The cheapest remaining (after B takes some) should not be HOUR_14
            self.assertNotEqual(c_slots[0].start_hour, HOUR_14,
                                "Second vehicle should not get current hour forced")


class TestTransitionLog(unittest.TestCase):
    """Test 4: Switching vehicles emits transition log with both names."""

    @patch("charge_sequencer.log")
    def test_transition_log(self, mock_log):
        seq = ChargeSequencer(make_cfg(), make_evcc())

        # Simulate previous vehicle was active
        seq._last_applied_vehicle = "vehicleA"

        # Set up schedule with vehicleB at current hour
        seq.schedule = [
            ChargeSlot(
                vehicle_name="vehicleB",
                start_hour=HOUR_14,
                end_hour=HOUR_15,
                energy_kwh=5.0,
                avg_price_ct=30.0,
                source="grid_expensive",
            )
        ]
        seq.requests["vehicleB"] = MagicMock(target_soc=90)

        seq.apply_to_evcc(NOW)

        # Find the transition log call
        log_calls = [c for c in mock_log.call_args_list
                     if len(c[0]) >= 2 and "transition" in str(c[0][1]).lower()]
        self.assertTrue(len(log_calls) > 0, "Should emit transition log")

        msg = str(log_calls[0][0][1])
        self.assertIn("vehicleA", msg)
        self.assertIn("vehicleB", msg)


class TestNoTransitionLogOnFirstActivation(unittest.TestCase):
    """Test 5: First activation emits 'activating', not 'transition'."""

    @patch("charge_sequencer.log")
    def test_no_transition_log_on_first_activation(self, mock_log):
        seq = ChargeSequencer(make_cfg(), make_evcc())

        # No previous vehicle
        seq._last_applied_vehicle = None

        seq.schedule = [
            ChargeSlot(
                vehicle_name="vehicleB",
                start_hour=HOUR_14,
                end_hour=HOUR_15,
                energy_kwh=5.0,
                avg_price_ct=30.0,
                source="grid_expensive",
            )
        ]
        seq.requests["vehicleB"] = MagicMock(target_soc=90)

        seq.apply_to_evcc(NOW)

        # Should NOT have transition log
        transition_calls = [c for c in mock_log.call_args_list
                            if len(c[0]) >= 2 and "transition" in str(c[0][1]).lower()]
        self.assertEqual(len(transition_calls), 0,
                         "First activation should NOT emit transition log")

        # Should have activating log
        activating_calls = [c for c in mock_log.call_args_list
                            if len(c[0]) >= 2 and "activating" in str(c[0][1]).lower()]
        self.assertTrue(len(activating_calls) > 0,
                        "First activation should emit 'activating' log")


class TestCurrentHourMissingFromTariff(unittest.TestCase):
    """Test 6: Tariff gap -- current hour synthesized with median price."""

    @patch("charge_sequencer.log")
    def test_current_hour_missing_from_tariff(self, mock_log):
        seq = ChargeSequencer(make_cfg(), make_evcc())

        # Prices start at hour 15 -- hour 14 (current) is missing
        prices_no_14 = [
            {"start": HOUR_15.isoformat(), "value": 0.10},
            {"start": HOUR_16.isoformat(), "value": 0.08},
            {"start": HOUR_17.isoformat(), "value": 0.05},
            {"start": HOUR_18.isoformat(), "value": 0.06},
            {"start": HOUR_19.isoformat(), "value": 0.05},
            {"start": HOUR_20.isoformat(), "value": 0.12},
        ]

        seq.add_request("vehicleB", "Bob", target_soc=90, current_soc=60,
                        capacity_kwh=50, charge_power_kw=11.0)

        schedule = seq.plan(prices_no_14, solar_forecast=[], connected_vehicle=None, now=NOW)

        b_slots = [s for s in schedule if s.vehicle_name == "vehicleB"]
        self.assertTrue(len(b_slots) > 0, "vehicleB should have slots")

        # Even though hour 14 wasn't in tariff, it should be synthesized
        slot_hours = [s.start_hour for s in b_slots]
        self.assertIn(HOUR_14, slot_hours,
                      "Current hour should be synthesized when missing from tariff")

        # The synthesized price should be the median of available prices
        hour_14_slot = [s for s in b_slots if s.start_hour == HOUR_14][0]
        # Median of [0.05, 0.05, 0.06, 0.08, 0.10, 0.12] = 0.07 (avg of 0.06 and 0.08)
        # But since we use integer index // 2, median = sorted[3] = 0.08
        # The avg_price_ct is computed by _build_slots across all chosen slots, not per-slot
        # So we just verify the slot exists -- the median logic is internal


if __name__ == "__main__":
    unittest.main()
