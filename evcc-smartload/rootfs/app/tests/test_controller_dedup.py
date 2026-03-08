"""
Tests for Controller.apply() command deduplication.

Verifies that redundant evcc API calls are skipped when
battery/EV action + limit values haven't changed.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for mod_name in ["requests", "numpy", "yaml", "scipy", "scipy.optimize"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

from state import Action
from controller import Controller


def make_evcc():
    evcc = MagicMock()
    evcc.set_battery_grid_charge_limit = MagicMock()
    evcc.clear_battery_grid_charge_limit = MagicMock()
    evcc.set_smart_cost_limit = MagicMock()
    return evcc


def make_cfg():
    cfg = MagicMock()
    cfg.battery_to_ev_dynamic_limit = False
    return cfg


class TestBatteryDedup(unittest.TestCase):

    def test_first_call_always_sends(self):
        """First apply() after init always sends API call."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        ctrl.apply(Action(battery_action=1, ev_action=0, battery_limit_eur=0.10))
        evcc.set_battery_grid_charge_limit.assert_called_once_with(0.10)

    def test_identical_call_skipped(self):
        """Two identical apply() calls -> evcc API called only once."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        action = Action(battery_action=1, ev_action=0, battery_limit_eur=0.10)
        ctrl.apply(action)
        ctrl.apply(action)

        evcc.set_battery_grid_charge_limit.assert_called_once()

    def test_different_limit_sends_again(self):
        """Changed battery_limit_eur -> API called again."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        ctrl.apply(Action(battery_action=1, ev_action=0, battery_limit_eur=0.10))
        ctrl.apply(Action(battery_action=1, ev_action=0, battery_limit_eur=0.20))

        self.assertEqual(evcc.set_battery_grid_charge_limit.call_count, 2)

    def test_switch_bat5_to_bat6_sends(self):
        """Switching from PV-only (5) to discharge (6) sends API call."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        ctrl.apply(Action(battery_action=5, ev_action=0))
        evcc.set_battery_grid_charge_limit.assert_called_once_with(0.0)

        ctrl.apply(Action(battery_action=6, ev_action=0))
        evcc.clear_battery_grid_charge_limit.assert_called_once()

    def test_repeated_bat5_skipped(self):
        """Two consecutive PV-only (5) calls -> only one API call."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        ctrl.apply(Action(battery_action=5, ev_action=0))
        ctrl.apply(Action(battery_action=5, ev_action=0))

        evcc.set_battery_grid_charge_limit.assert_called_once()

    def test_repeated_bat6_skipped(self):
        """Two consecutive discharge (6) calls -> only one clear call."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        ctrl.apply(Action(battery_action=6, ev_action=0))
        ctrl.apply(Action(battery_action=6, ev_action=0))

        evcc.clear_battery_grid_charge_limit.assert_called_once()


class TestEvDedup(unittest.TestCase):

    def test_identical_ev_call_skipped(self):
        """Two identical EV apply() calls -> set_smart_cost_limit called once."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        action = Action(battery_action=0, ev_action=1, ev_limit_eur=0.15)
        ctrl.apply(action)
        ctrl.apply(action)

        evcc.set_smart_cost_limit.assert_called_once()

    def test_different_ev_limit_sends_again(self):
        """Changed ev_limit_eur -> API called again."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        ctrl.apply(Action(battery_action=0, ev_action=1, ev_limit_eur=0.15))
        ctrl.apply(Action(battery_action=0, ev_action=1, ev_limit_eur=0.25))

        self.assertEqual(evcc.set_smart_cost_limit.call_count, 2)

    def test_ev_pv_only_dedup(self):
        """Two consecutive EV PV-only (4) calls -> only one API call."""
        evcc = make_evcc()
        ctrl = Controller(evcc, make_cfg())

        ctrl.apply(Action(battery_action=0, ev_action=4))
        ctrl.apply(Action(battery_action=0, ev_action=4))

        evcc.set_smart_cost_limit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
