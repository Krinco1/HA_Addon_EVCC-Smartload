"""
Decision Log – "Was sehe ich, was plane ich, was mache ich?"

Collects system observations, reasoning, and actions in a human-readable log.
Used by the dashboard to show transparent decision-making.
"""

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional


class DecisionEntry:
    """A single decision log entry."""
    __slots__ = ("ts", "category", "icon", "text", "details", "source")

    def __init__(self, category: str, icon: str, text: str,
                 details: str = "", source: str = "system"):
        self.ts = datetime.now(timezone.utc)
        self.category = category  # observe, plan, action, warning, rl
        self.icon = icon
        self.text = text
        self.details = details
        self.source = source  # system, controller, rl, vehicle, battery

    def to_dict(self) -> dict:
        return {
            "ts": self.ts.isoformat(),
            "ts_local": self.ts.astimezone().strftime("%H:%M:%S"),
            "category": self.category,
            "icon": self.icon,
            "text": self.text,
            "details": self.details,
            "source": self.source,
        }


class DecisionLog:
    """Thread-safe ring buffer of decision log entries."""

    def __init__(self, max_entries: int = 100):
        self._entries: deque = deque(maxlen=max_entries)
        self._lock = threading.Lock()

    def observe(self, text: str, details: str = "", source: str = "system"):
        """Log an observation (what the system sees)."""
        self._add("observe", "👁️", text, details, source)

    def plan(self, text: str, details: str = "", source: str = "system"):
        """Log a planning decision (what the system intends)."""
        self._add("plan", "🧠", text, details, source)

    def action(self, text: str, details: str = "", source: str = "controller"):
        """Log an executed action (what the system does)."""
        self._add("action", "⚡", text, details, source)

    def warning(self, text: str, details: str = "", source: str = "system"):
        """Log a warning or unusual condition."""
        self._add("warning", "⚠️", text, details, source)

    def rl(self, text: str, details: str = "", source: str = "rl"):
        """Log an RL-related decision."""
        self._add("rl", "🤖", text, details, source)

    def _add(self, category: str, icon: str, text: str, details: str, source: str):
        entry = DecisionEntry(category, icon, text, details, source)
        with self._lock:
            self._entries.append(entry)

    def get_recent(self, n: int = 30) -> List[dict]:
        with self._lock:
            entries = list(self._entries)
        return [e.to_dict() for e in entries[-n:]]

    def get_last_cycle_summary(self) -> dict:
        """Get a summary of the most recent decision cycle."""
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return {"observations": [], "plans": [], "actions": []}

        # Find entries from the last ~120 seconds (one cycle)
        now = datetime.now(timezone.utc)
        recent = [e for e in entries
                  if (now - e.ts).total_seconds() < 120]

        return {
            "observations": [e.to_dict() for e in recent if e.category == "observe"],
            "plans": [e.to_dict() for e in recent if e.category == "plan"],
            "actions": [e.to_dict() for e in recent if e.category in ("action", "rl")],
            "warnings": [e.to_dict() for e in recent if e.category == "warning"],
        }


def log_main_cycle(dlog: "DecisionLog", state, cfg, vehicles: Dict,
                    lp_action, rl_action, comparator, tariffs: list,
                    solar_forecast: list = None):
    """Called each main loop iteration to log the full decision reasoning."""

    if not state:
        dlog.warning("Kein System-Status verfügbar")
        return

    # --- Observations ---
    price_ct = state.current_price * 100 if state.current_price else 0
    bat_soc = state.battery_soc
    pv_kw = state.pv_power / 1000 if state.pv_power else 0
    home_kw = state.home_power / 1000 if state.home_power else 0

    dlog.observe(
        f"Strompreis {price_ct:.1f}ct · Batterie {bat_soc:.0f}% · PV {pv_kw:.1f}kW · Haus {home_kw:.1f}kW",
        source="system"
    )

    bat_limit = cfg.battery_max_price_ct
    ev_limit = cfg.ev_max_price_ct

    # Vehicle observations
    for name, v in vehicles.items():
        soc = v.get_effective_soc()
        connected = "🔌 am Wallbox" if v.connected_to_wallbox else "🅿️ nicht verbunden"
        stale = " ⚠️ VERALTET" if v.is_data_stale() else ""
        source = v.data_source
        dlog.observe(
            f"{name}: {soc:.0f}% ({source}) · {connected}{stale}",
            details=f"Kapazität: {v.capacity_kwh}kWh, Ziel: {cfg.ev_target_soc}%",
            source="vehicle"
        )

    # --- Planning / Reasoning ---
    # Battery decision
    if price_ct <= bat_limit:
        dlog.plan(
            f"Batterie: Laden erlaubt (Preis {price_ct:.1f}ct ≤ Limit {bat_limit}ct)",
            source="battery"
        )
    else:
        dlog.plan(
            f"Batterie: Halten/Entladen (Preis {price_ct:.1f}ct > Limit {bat_limit}ct)",
            source="battery"
        )

    # EV decisions
    for name, v in vehicles.items():
        soc = v.get_effective_soc()
        need = max(0, (cfg.ev_target_soc - soc) / 100 * v.capacity_kwh)
        if need < 1:
            continue
        if v.connected_to_wallbox:
            if price_ct <= ev_limit:
                dlog.plan(
                    f"{name}: Laden empfohlen ({need:.0f}kWh Bedarf, Preis {price_ct:.1f}ct ≤ {ev_limit}ct)",
                    source="vehicle"
                )
            else:
                dlog.plan(
                    f"{name}: Warten auf günstigen Preis ({need:.0f}kWh Bedarf, Preis {price_ct:.1f}ct > {ev_limit}ct)",
                    source="vehicle"
                )
        else:
            dlog.plan(
                f"{name}: {need:.0f}kWh Bedarf, aber nicht am Wallbox → Keine Aktion",
                source="vehicle"
            )

    # Solar impact
    if pv_kw > 0.5:
        surplus = max(0, pv_kw - home_kw)
        if surplus > 0.3:
            dlog.observe(
                f"PV-Überschuss: {surplus:.1f}kW → wird genutzt",
                source="system"
            )
        else:
            dlog.observe(
                f"PV reicht nicht für Überschuss (PV {pv_kw:.1f}kW < Haus {home_kw:.1f}kW)",
                source="system"
            )

    # --- Actions ---
    if lp_action:
        if lp_action.battery_limit_eur is not None:
            dlog.action(
                f"LP → Batterie-Limit: {lp_action.battery_limit_eur*100:.1f}ct",
                source="controller"
            )
        if lp_action.ev_limit_eur is not None:
            dlog.action(
                f"LP → EV-Smart-Cost-Limit: {lp_action.ev_limit_eur*100:.1f}ct",
                source="controller"
            )

    # RL vs LP
    try:
        rl_mode = comparator.rl_ready
        n_comps = len(comparator.comparisons) if comparator.comparisons else 0
        rl_wins = comparator.rl_wins
        win_pct = (rl_wins / max(1, n_comps)) * 100

        if rl_mode:
            dlog.rl(
                f"RL aktiv (Win-Rate: {win_pct:.0f}%, {n_comps} Vergleiche)",
                source="rl"
            )
        else:
            dlog.rl(
                f"RL im Schatten-Modus (Win-Rate: {win_pct:.0f}%, {n_comps} Vergleiche)",
                source="rl"
            )

        if rl_action and lp_action:
            rl_bat = rl_action.battery_limit_eur
            lp_bat = lp_action.battery_limit_eur
            if rl_bat is not None and lp_bat is not None and abs(rl_bat - lp_bat) > 0.001:
                dlog.rl(
                    f"RL weicht ab: Bat-Limit {rl_bat*100:.1f}ct (LP: {lp_bat*100:.1f}ct)",
                    source="rl"
                )
    except Exception:
        pass
