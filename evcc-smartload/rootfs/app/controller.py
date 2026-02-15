"""
Controller – applies optimiser/RL actions to evcc.
"""

from typing import Optional

from config import Config
from evcc_client import EvccClient
from logging_util import log
from state import Action


class Controller:
    """Translates Action objects into evcc API calls."""

    def __init__(self, evcc: EvccClient, cfg: Config):
        self.evcc = evcc
        self.cfg = cfg
        self.last_action: Optional[Action] = None
        self._bat_to_ev_active = False

    def apply(self, action: Action) -> float:
        """Apply action and return estimated cost (placeholder, refined later)."""

        # Battery
        if action.battery_limit_eur is not None and action.battery_limit_eur > 0:
            self.evcc.set_battery_grid_charge_limit(action.battery_limit_eur)
        else:
            self.evcc.clear_battery_grid_charge_limit()

        # EV
        if action.ev_limit_eur is not None:
            self.evcc.set_smart_cost_limit(max(0, action.ev_limit_eur))

        self.last_action = action
        return 0.0

    def apply_battery_to_ev(self, bat_to_ev: dict, ev_connected: bool) -> bool:
        """Activate or deactivate battery-to-EV discharge mode.
        
        When profitable:
          - Set battery to 'normal' (allow discharge)
          - Enable discharge control (battery can power loadpoints)
          - Set loadpoint to 'now' (force charge EV immediately)
        
        When not profitable or no EV:
          - Restore battery to 'normal' + disable forced EV charging
        """
        if not bat_to_ev:
            return False

        is_profitable = bat_to_ev.get("is_profitable", False)
        usable = bat_to_ev.get("usable_kwh", 0)
        should_activate = is_profitable and usable > 0.5 and ev_connected

        if should_activate and not self._bat_to_ev_active:
            log("info", f"🔋→🚗 Aktiviere Batterie-Entladung für EV "
                f"(spare {bat_to_ev.get('savings_ct_per_kwh', 0):.0f}ct/kWh, "
                f"{usable:.0f}kWh verfügbar)")
            self.evcc.set_battery_mode("normal")
            self.evcc.set_battery_discharge_control(True)
            self.evcc.set_loadpoint_mode(1, "now")
            self._bat_to_ev_active = True
            return True

        elif not should_activate and self._bat_to_ev_active:
            log("info", "🔋→🚗 Deaktiviere Batterie-Entladung für EV")
            self.evcc.set_battery_discharge_control(True)  # Keep discharge on
            self.evcc.set_loadpoint_mode(1, "minpv")  # Back to PV-mode
            self._bat_to_ev_active = False
            return False

        return self._bat_to_ev_active
