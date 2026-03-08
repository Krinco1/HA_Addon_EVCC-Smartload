"""Tests for 'defers to evcc' decision log entry during PV surplus."""

import unittest
from unittest.mock import MagicMock


def _maybe_log_defers(decision_log, state, mode_status):
    """Extract the defers-to-evcc log logic from main.py for testing."""
    if (mode_status.get("active") and
        mode_status.get("current_mode") == "pv" and
        state.pv_power > state.home_power + 300):
        decision_log.observe(
            "SmartLoad defers to evcc (PV-Surplus, Modus: pv)",
            source="system",
        )


class TestDefersToEvccLog(unittest.TestCase):
    """Verify defers-to-evcc decision log entry conditions."""

    def test_pv_mode_with_surplus_logs_defers(self):
        """When mode=pv, active=True, PV surplus > 300W -> log defers."""
        dlog = MagicMock()
        state = MagicMock()
        state.pv_power = 3000
        state.home_power = 1000

        mode_status = {"active": True, "current_mode": "pv"}

        _maybe_log_defers(dlog, state, mode_status)

        dlog.observe.assert_called_once()
        call_text = dlog.observe.call_args[0][0]
        self.assertIn("defers to evcc", call_text)

    def test_mode_not_pv_no_log(self):
        """When mode is 'now' (not 'pv'), no defers log."""
        dlog = MagicMock()
        state = MagicMock()
        state.pv_power = 3000
        state.home_power = 1000

        mode_status = {"active": True, "current_mode": "now"}

        _maybe_log_defers(dlog, state, mode_status)

        dlog.observe.assert_not_called()

    def test_low_pv_surplus_no_log(self):
        """When PV surplus <= 300W, no defers log."""
        dlog = MagicMock()
        state = MagicMock()
        state.pv_power = 1200
        state.home_power = 1000  # surplus = 200W < 300W

        mode_status = {"active": True, "current_mode": "pv"}

        _maybe_log_defers(dlog, state, mode_status)

        dlog.observe.assert_not_called()

    def test_mode_not_active_no_log(self):
        """When mode controller is not active, no defers log."""
        dlog = MagicMock()
        state = MagicMock()
        state.pv_power = 3000
        state.home_power = 1000

        mode_status = {"active": False, "current_mode": "pv"}

        _maybe_log_defers(dlog, state, mode_status)

        dlog.observe.assert_not_called()


class TestDefersToEvccMainIntegration(unittest.TestCase):
    """Verify main.py contains the defers-to-evcc log code."""

    def test_main_py_has_defers_to_evcc_code(self):
        """main.py must contain 'defers to evcc' string."""
        import os
        main_path = os.path.join(os.path.dirname(__file__), "..", "main.py")
        with open(main_path, "r") as f:
            source = f.read()

        self.assertIn("defers to evcc", source,
                      "main.py must contain 'defers to evcc' decision log entry")


if __name__ == "__main__":
    unittest.main()
