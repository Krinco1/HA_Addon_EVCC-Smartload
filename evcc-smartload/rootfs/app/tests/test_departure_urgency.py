"""Tests for departure urgency calculation in main loop."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


class TestDepartureUrgency(unittest.TestCase):
    """Verify departure_store.get() is called correctly and urgency flag propagates."""

    def _calc_urgency(self, departure_store, state, cfg):
        """Extract the departure urgency logic block from main.py for testing."""
        _departure_urgent = False
        if state.ev_connected and departure_store:
            _dep_time = departure_store.get(state.ev_name or "")
            if _dep_time:
                _hours_left = (_dep_time - datetime.now(timezone.utc)).total_seconds() / 3600
                _soc_needed = max(0, cfg.ev_target_soc - state.ev_soc)
                _hours_needed = (_soc_needed / 100 * (state.ev_capacity_kwh or 30)) / (state.ev_charge_power_kw or 11)
                _departure_urgent = _hours_left < _hours_needed * 1.3
        return _departure_urgent

    def test_get_method_called_not_get_departure(self):
        """departure_store.get() must be called, not get_departure()."""
        store = MagicMock()
        store.get.return_value = datetime.now(timezone.utc) + timedelta(hours=2)

        state = MagicMock()
        state.ev_connected = True
        state.ev_name = "kona"
        state.ev_soc = 20
        state.ev_capacity_kwh = 64
        state.ev_charge_power_kw = 11

        cfg = MagicMock()
        cfg.ev_target_soc = 80

        self._calc_urgency(store, state, cfg)

        store.get.assert_called_once_with("kona")
        self.assertFalse(hasattr(store, 'get_departure') and store.get_departure.called,
                         "get_departure() should NOT be used")

    def test_departure_imminent_returns_urgent_true(self):
        """When hours_left < hours_needed * 1.3, departure is urgent."""
        store = MagicMock()
        # Departure in 2 hours, but need ~5 hours to charge -> urgent
        store.get.return_value = datetime.now(timezone.utc) + timedelta(hours=2)

        state = MagicMock()
        state.ev_connected = True
        state.ev_name = "kona"
        state.ev_soc = 20
        state.ev_capacity_kwh = 64
        state.ev_charge_power_kw = 11

        cfg = MagicMock()
        cfg.ev_target_soc = 80

        result = self._calc_urgency(store, state, cfg)
        self.assertTrue(result, "Should be urgent when departure is imminent")

    def test_departure_far_away_returns_urgent_false(self):
        """When departure is far away, not urgent."""
        store = MagicMock()
        # Departure in 24 hours, only need ~3.5 hours to charge -> not urgent
        store.get.return_value = datetime.now(timezone.utc) + timedelta(hours=24)

        state = MagicMock()
        state.ev_connected = True
        state.ev_name = "kona"
        state.ev_soc = 20
        state.ev_capacity_kwh = 64
        state.ev_charge_power_kw = 11

        cfg = MagicMock()
        cfg.ev_target_soc = 80

        result = self._calc_urgency(store, state, cfg)
        self.assertFalse(result, "Should NOT be urgent when departure is far away")

    def test_no_departure_store_stays_false(self):
        """When departure_store is None, _departure_urgent stays False."""
        state = MagicMock()
        state.ev_connected = True

        cfg = MagicMock()

        result = self._calc_urgency(None, state, cfg)
        self.assertFalse(result)

    def test_ev_not_connected_stays_false(self):
        """When EV is not connected, urgency is False regardless."""
        store = MagicMock()
        state = MagicMock()
        state.ev_connected = False

        cfg = MagicMock()

        result = self._calc_urgency(store, state, cfg)
        self.assertFalse(result)
        store.get.assert_not_called()


class TestDepartureUrgencyMainIntegration(unittest.TestCase):
    """Verify main.py actually calls departure_store.get() (not get_departure)."""

    def test_main_py_uses_get_not_get_departure(self):
        """Grep main.py source to confirm .get() is used."""
        import os
        main_path = os.path.join(os.path.dirname(__file__), "..", "main.py")
        with open(main_path, "r") as f:
            source = f.read()

        # The bug: main.py calls get_departure() which doesn't exist
        self.assertNotIn("departure_store.get_departure(", source,
                         "main.py must NOT call get_departure() - method doesn't exist")
        self.assertIn("departure_store.get(", source,
                      "main.py must call departure_store.get()")


if __name__ == "__main__":
    unittest.main()
