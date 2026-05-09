"""
Component bootstrap — extracted from main.py in v6.6.0.

Responsibility:
  - Apply config validation defaults.
  - Build all SmartLoad subsystems (forecaster, planner, RL agent, sequencer,
    notifier, override manager, mode controller, learners, …).
  - Wire late-bound cross-references (notifier ↔ sequencer ↔ override manager).
  - Track per-component init health so the dashboard can surface degraded
    subsystems instead of silently disabling them.

Pre-v6.6.0 main.py had ~250 lines of init wrapped in repeated try/except blocks.
That made it impossible to:
  - test init in isolation,
  - tell at a glance which optional subsystems were available,
  - change init order without scrolling 200 lines.

Components is a plain dataclass — main.py rebinds its fields to local variables
to keep the existing decision loop unchanged. A future refactor will fold the
loop into Components methods.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

from logging_util import log


# =============================================================================
# Health tracking
# =============================================================================

@dataclass
class ComponentHealth:
    """One subsystem's init outcome.

    status:
      - "ok"        — initialized successfully
      - "failed"    — exception during init; subsystem unavailable
      - "disabled"  — config opted out (e.g. sequencer_enabled=False)
    """
    name: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


# =============================================================================
# Components container
# =============================================================================

@dataclass
class Components:
    """All initialized subsystems, plus per-component health log."""

    # --- Core (must succeed; if any of these raise, startup aborts) ---
    cfg: Any
    evcc: Any
    influx: Any
    plan_snapshotter: Any
    manual_store: Any
    consumption_forecaster: Any
    pv_forecaster: Any
    vehicle_monitor: Any
    collector: Any
    optimizer: Any
    event_detector: Any
    comparator: Any
    controller: Any
    rl_devices: Any
    driver_mgr: Any
    decision_log: Any

    # --- Optional / silent-degrade ---
    horizon_planner: Optional[Any] = None
    buffer_calc: Optional[Any] = None
    rl_agent: Optional[Any] = None
    seasonal_learner: Optional[Any] = None
    forecast_reliability: Optional[Any] = None
    reaction_timing: Optional[Any] = None
    sequencer: Optional[Any] = None
    telegram_bot: Optional[Any] = None
    notifier: Optional[Any] = None
    override_manager: Optional[Any] = None
    departure_store: Optional[Any] = None
    mode_controller: Optional[Any] = None

    # --- Init metadata ---
    health: List[ComponentHealth] = field(default_factory=list)
    ha_discovery_result: dict = field(default_factory=lambda: {"status": "pending"})
    last_pv_refresh: float = 0.0


# =============================================================================
# Config validation helpers (extracted from main.py)
# =============================================================================

def apply_validation_defaults(cfg, config_errors) -> None:
    """Apply safe defaults for non-critical config warnings before I/O starts."""
    for e in config_errors:
        if e.severity != "warning":
            continue
        if e.field == "battery_max_price_ct":
            log("warning", f"Setze battery_max_price_ct auf 25.0ct (war: {cfg.battery_max_price_ct})")
            cfg.battery_max_price_ct = 25.0
        elif e.field == "ev_max_price_ct":
            log("warning", f"Setze ev_max_price_ct auf 30.0ct (war: {cfg.ev_max_price_ct})")
            cfg.ev_max_price_ct = 30.0
        elif e.field == "decision_interval_minutes":
            log("warning", f"Setze decision_interval_minutes auf 15 (war: {cfg.decision_interval_minutes})")
            cfg.decision_interval_minutes = 15


# =============================================================================
# bootstrap() — orchestrated init
# =============================================================================

def bootstrap(cfg) -> Components:
    """Build all SmartLoad subsystems. Caller must already have:
      - validated cfg (including critical-error gate),
      - constructed StateStore + WebServer (passed in via wire_web()).
    """
    # Imports are inline so test code can stub modules before import.
    from evcc_client import EvccClient
    from influxdb_client import InfluxDBClient
    from plan_snapshotter import PlanSnapshotter
    from state import ManualSocStore
    from forecaster import ConsumptionForecaster, PVForecaster
    from forecaster.ha_energy import run_entity_discovery
    from vehicle_monitor import DataCollector, VehicleMonitor
    from optimizer import HolisticOptimizer, EventDetector
    from comparator import Comparator, RLDeviceController
    from controller import Controller
    from driver_manager import DriverManager
    from decision_log import DecisionLog
    from charge_sequencer import ChargeSequencer

    health: List[ComponentHealth] = []

    def ok(name: str, detail: str = ""):
        health.append(ComponentHealth(name, "ok", detail))

    def failed(name: str, exc: Exception, level: str = "warning"):
        health.append(ComponentHealth(name, "failed", str(exc)))
        log(level, f"{name}: init failed ({exc})")

    def disabled(name: str, reason: str):
        health.append(ComponentHealth(name, "disabled", reason))
        log("info", f"{name}: disabled ({reason})")

    # --- Core (no try/except — any failure here is a startup blocker) ---
    evcc = EvccClient(cfg); ok("EvccClient")
    influx = InfluxDBClient(cfg); ok("InfluxDBClient")
    plan_snapshotter = PlanSnapshotter(influx); ok("PlanSnapshotter")
    manual_store = ManualSocStore(); ok("ManualSocStore")

    consumption_forecaster = ConsumptionForecaster(influx, cfg); ok("ConsumptionForecaster")
    pv_forecaster = PVForecaster(evcc); ok("PVForecaster")

    # HA entity discovery (background, non-blocking)
    ha_discovery_result = {"status": "pending"}
    if getattr(cfg, "ha_url", None) and getattr(cfg, "ha_token", None):
        def _ha_discover():
            ha_discovery_result.update(run_entity_discovery(cfg.ha_url, cfg.ha_token))
        threading.Thread(target=_ha_discover, daemon=True).start()
        ok("HA Entity Discovery", "background thread started")
    else:
        disabled("HA Entity Discovery", "ha_url / ha_token not configured")

    pv_forecaster.refresh()
    last_pv_refresh = time.time()

    vehicle_monitor = VehicleMonitor(evcc, cfg, manual_store); ok("VehicleMonitor")
    collector = DataCollector(evcc, influx, cfg, vehicle_monitor); ok("DataCollector")
    optimizer = HolisticOptimizer(cfg); ok("HolisticOptimizer")

    # --- Optional: HorizonPlanner ---
    horizon_planner = None
    try:
        from optimizer.planner import HorizonPlanner
        horizon_planner = HorizonPlanner(cfg)
        ok("HorizonPlanner", "scipy/HiGHS LP solver")
        log("info", "HorizonPlanner: initialized (scipy/HiGHS LP solver)")
    except ImportError as e:
        failed("HorizonPlanner", e)
        log("warning", f"HorizonPlanner: scipy not available ({e}), using HolisticOptimizer only")
    except Exception as e:
        failed("HorizonPlanner", e)
        log("warning", f"HorizonPlanner: init failed ({e}), using HolisticOptimizer only")

    # --- Optional: DynamicBufferCalc ---
    buffer_calc = None
    try:
        from dynamic_buffer import DynamicBufferCalc
        buffer_calc = DynamicBufferCalc(cfg, evcc); ok("DynamicBufferCalc")
        log("info", "DynamicBufferCalc: initialized")
    except Exception as e:
        failed("DynamicBufferCalc", e)
        log("warning", f"DynamicBufferCalc: init failed ({e}), buffer management disabled")

    # --- Optional: ResidualRLAgent ---
    rl_agent = None
    try:
        from rl_agent import ResidualRLAgent
        rl_agent = ResidualRLAgent(cfg); ok("ResidualRLAgent", f"mode={rl_agent.mode}")
        log("info", f"ResidualRLAgent: initialized (mode={rl_agent.mode})")
    except Exception as e:
        failed("ResidualRLAgent", e)
        log("warning", f"ResidualRLAgent: init failed ({e}), RL corrections disabled")

    event_detector = EventDetector(); ok("EventDetector")
    comparator = Comparator(cfg); ok("Comparator")
    controller = Controller(evcc, cfg); ok("Controller")
    rl_devices = RLDeviceController(cfg); ok("RLDeviceController")

    # --- Optional learners ---
    seasonal_learner = None
    try:
        from seasonal_learner import SeasonalLearner
        seasonal_learner = SeasonalLearner()
        ok("SeasonalLearner", f"{seasonal_learner.populated_cell_count()} cells populated")
        log("info", f"SeasonalLearner: {seasonal_learner.populated_cell_count()} cells populated")
    except Exception as e:
        failed("SeasonalLearner", e)
        log("warning", f"SeasonalLearner init failed: {e}")

    forecast_reliability = None
    try:
        from forecast_reliability import ForecastReliabilityTracker
        forecast_reliability = ForecastReliabilityTracker(); ok("ForecastReliabilityTracker")
        log("info", "ForecastReliabilityTracker initialized")
    except Exception as e:
        failed("ForecastReliabilityTracker", e)
        log("warning", f"ForecastReliabilityTracker init failed: {e}")

    reaction_timing = None
    try:
        from reaction_timing import ReactionTimingTracker
        reaction_timing = ReactionTimingTracker(); ok("ReactionTimingTracker")
        log("info", "ReactionTimingTracker initialized")
    except Exception as e:
        failed("ReactionTimingTracker", e)
        log("warning", f"ReactionTimingTracker init failed: {e}")

    # --- Sequencer (config gate, not exception gate) ---
    sequencer = None
    if cfg.sequencer_enabled:
        sequencer = ChargeSequencer(cfg, evcc); ok("ChargeSequencer")
    else:
        disabled("ChargeSequencer", "sequencer_enabled=false in config")

    # --- DriverManager + Telegram (depends on sequencer for soc-response wiring) ---
    driver_mgr = DriverManager(); ok("DriverManager", f"{len(driver_mgr.drivers)} driver(s)")
    telegram_bot = None
    notifier = None
    if driver_mgr.telegram_enabled:
        try:
            from notification import TelegramBot, NotificationManager
            telegram_bot = TelegramBot(driver_mgr.telegram_bot_token)
            notifier = NotificationManager(
                bot=telegram_bot,
                driver_manager=driver_mgr,
                on_soc_response=_make_soc_response_handler(sequencer, vehicle_monitor),
            )
            telegram_bot.start_polling()
            ok("TelegramBot", f"polling for {len(driver_mgr.drivers)} driver(s)")
            log("info", f"Telegram Bot aktiv für {len(driver_mgr.drivers)} Fahrer")
        except Exception as e:
            failed("TelegramBot", e, level="error")
            log("error", f"Telegram setup failed: {e}")
            notifier = None
    else:
        disabled("TelegramBot", "telegram_enabled=false / no token configured")

    # --- OverrideManager (Boost Charge) ---
    override_manager = None
    try:
        from override_manager import OverrideManager
        override_manager = OverrideManager(cfg, evcc, notifier); ok("OverrideManager")
        log("info", "OverrideManager: initialized")
    except Exception as e:
        failed("OverrideManager", e)
        log("warning", f"OverrideManager: init failed ({e}), boost-charge disabled")

    if notifier is not None and override_manager is not None:
        notifier.override_manager = override_manager

    # --- DepartureTimeStore ---
    departure_store = None
    try:
        from departure_store import DepartureTimeStore
        departure_store = DepartureTimeStore(default_hour=cfg.ev_charge_deadline_hour)
        ok("DepartureTimeStore")
        log("info", "DepartureTimeStore: initialized")
    except Exception as e:
        failed("DepartureTimeStore", e)
        log("warning", f"DepartureTimeStore: init failed ({e}), departure queries disabled")

    if notifier is not None and departure_store is not None:
        notifier.departure_store = departure_store
    if sequencer is not None and departure_store is not None:
        sequencer.departure_store = departure_store

    # --- EvccModeController ---
    mode_controller = None
    try:
        from evcc_mode_controller import EvccModeController
        mode_controller = EvccModeController(evcc, cfg); ok("EvccModeController")
        log("info", "EvccModeController: initialized")
    except Exception as e:
        failed("EvccModeController", e)
        log("warning", f"EvccModeController: init failed ({e}), mode control disabled")

    # v6.5.0: ModeController owns the mode-write channel — Sequencer must defer.
    if mode_controller is not None and sequencer is not None:
        sequencer.mode_writes_owned_externally = True

    # --- RL device registration ---
    rl_devices.get_device_mode("battery")
    for vp in cfg.vehicle_providers:
        vname = vp.get("evcc_name") or vp.get("name", "")
        if vname:
            rl_devices.get_device_mode(vname)
    rl_devices.dedup_case_duplicates()

    decision_log = DecisionLog(max_entries=100); ok("DecisionLog")

    return Components(
        cfg=cfg,
        evcc=evcc, influx=influx, plan_snapshotter=plan_snapshotter,
        manual_store=manual_store,
        consumption_forecaster=consumption_forecaster, pv_forecaster=pv_forecaster,
        vehicle_monitor=vehicle_monitor, collector=collector,
        optimizer=optimizer, horizon_planner=horizon_planner,
        buffer_calc=buffer_calc, rl_agent=rl_agent,
        event_detector=event_detector, comparator=comparator,
        controller=controller, rl_devices=rl_devices,
        seasonal_learner=seasonal_learner,
        forecast_reliability=forecast_reliability,
        reaction_timing=reaction_timing,
        sequencer=sequencer, driver_mgr=driver_mgr,
        telegram_bot=telegram_bot, notifier=notifier,
        override_manager=override_manager, departure_store=departure_store,
        mode_controller=mode_controller,
        decision_log=decision_log,
        health=health,
        ha_discovery_result=ha_discovery_result,
        last_pv_refresh=last_pv_refresh,
    )


def wire_web(comp: Components, web) -> None:
    """Attach all components to the WebServer's late-bound attribute slots.

    Pre-v6.6.0 these 18 assignments lived in main.py. WebServer was started
    early (before bootstrap) so the error page is reachable on critical
    config errors; the attributes get filled here once components exist.
    """
    web.lp = comp.optimizer
    web.rl = comp.rl_agent
    web.comparator = comp.comparator
    web.events = comp.event_detector
    web.collector = comp.collector
    web.vehicle_monitor = comp.vehicle_monitor
    web.rl_devices = comp.rl_devices
    web.manual_store = comp.manual_store
    web.decision_log = comp.decision_log
    web.sequencer = comp.sequencer
    web.driver_mgr = comp.driver_mgr
    web.notifier = comp.notifier
    web.buffer_calc = comp.buffer_calc
    web.plan_snapshotter = comp.plan_snapshotter
    web.override_manager = comp.override_manager
    web.seasonal_learner = comp.seasonal_learner
    web.forecast_reliability = comp.forecast_reliability
    web.reaction_timing = comp.reaction_timing
    web.mode_controller = comp.mode_controller
    web.departure_store = comp.departure_store
    # v6.6.0: surface component health to the dashboard
    web.component_health = comp.health


def _make_soc_response_handler(sequencer, vehicle_monitor):
    """Build the on_soc_response callback for the Telegram bot.

    Lambda factored out so it can survive a future ``sequencer = None`` rebind
    via attribute capture rather than closure capture of the sequencer ref.
    """
    def _handle(vehicle_name: str, soc: int, chat_id):
        if sequencer is None:
            return
        vehicles = vehicle_monitor.get_all_vehicles()
        v = vehicles.get(vehicle_name)
        if not v:
            return
        sequencer.add_request(
            vehicle=vehicle_name,
            driver="",
            target_soc=soc,
            current_soc=v.get_effective_soc(),
            capacity_kwh=v.capacity_kwh,
            charge_power_kw=getattr(v, "charge_power_kw", None) or 11.0,
        )
    return _handle
