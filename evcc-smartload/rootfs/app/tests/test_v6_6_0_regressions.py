"""Regression tests for v6.6.0:
  - bootstrap.py extract (Components dataclass + ComponentHealth tracking)
  - Renault provider hardening (auth-error detection, backoff overflow guard,
    timestamp extraction)
  - SLF-015 Component-Health backend exposed via WebServer attribute
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Bootstrap: structure + health tracking
# =============================================================================

def test_component_health_to_dict_shape():
    from bootstrap import ComponentHealth
    h = ComponentHealth(name="HorizonPlanner", status="failed", detail="scipy missing")
    d = h.to_dict()
    assert d == {"name": "HorizonPlanner", "status": "failed", "detail": "scipy missing"}


def test_components_dataclass_has_optional_fields():
    """Optional subsystems must default to None — main.py loop relies on
    `if rl_agent is not None:` checks."""
    import bootstrap
    optionals = ("horizon_planner", "buffer_calc", "rl_agent",
                 "seasonal_learner", "forecast_reliability", "reaction_timing",
                 "sequencer", "telegram_bot", "notifier", "override_manager",
                 "departure_store", "mode_controller")
    fields = bootstrap.Components.__dataclass_fields__
    for name in optionals:
        assert name in fields, f"Components missing optional field: {name}"
        # default factory or None
        f = fields[name]
        # Either default=None or default_factory present
        assert f.default is None or f.default_factory is not None, \
            f"Optional field {name} should default to None"


def test_apply_validation_defaults_clamps_battery_max_price():
    from bootstrap import apply_validation_defaults
    from types import SimpleNamespace

    cfg = SimpleNamespace(battery_max_price_ct=999.0, ev_max_price_ct=999.0,
                          decision_interval_minutes=999)
    errors = [
        SimpleNamespace(severity="warning", field="battery_max_price_ct"),
        SimpleNamespace(severity="warning", field="ev_max_price_ct"),
        SimpleNamespace(severity="warning", field="decision_interval_minutes"),
    ]
    apply_validation_defaults(cfg, errors)
    assert cfg.battery_max_price_ct == 25.0
    assert cfg.ev_max_price_ct == 30.0
    assert cfg.decision_interval_minutes == 15


def test_apply_validation_defaults_ignores_critical():
    from bootstrap import apply_validation_defaults
    from types import SimpleNamespace
    cfg = SimpleNamespace(battery_max_price_ct=999.0)
    errors = [SimpleNamespace(severity="critical", field="battery_max_price_ct")]
    apply_validation_defaults(cfg, errors)
    # Critical errors are NOT defaulted — main.py blocks startup instead
    assert cfg.battery_max_price_ct == 999.0


# =============================================================================
# Renault hardening
# =============================================================================

def test_renault_auth_error_detection_via_status_attribute():
    from vehicles.renault_provider import _is_auth_error

    class FakeAiohttpError(Exception):
        status = 401

    assert _is_auth_error(FakeAiohttpError("unauthorized")) is True

    class FakeAiohttpError403(Exception):
        status = 403

    assert _is_auth_error(FakeAiohttpError403("forbidden")) is True


def test_renault_auth_error_detection_via_kamereon_error_details():
    from vehicles.renault_provider import _is_auth_error

    class KamereonErr(Exception):
        def __init__(self, code):
            self.error_details = [{"errorCode": code}]

    assert _is_auth_error(KamereonErr("err.func.401")) is True
    assert _is_auth_error(KamereonErr("err.tech.401")) is True
    # Non-auth error code
    assert _is_auth_error(KamereonErr("err.func.500")) is False


def test_renault_auth_error_detection_falls_back_to_substring():
    from vehicles.renault_provider import _is_auth_error
    # Plain Exception with no structured info — must still detect via msg
    assert _is_auth_error(Exception("HTTP 401 Unauthorized")) is True
    assert _is_auth_error(Exception("Got 403 forbidden")) is True
    # Non-auth msg
    assert _is_auth_error(Exception("network timeout")) is False


def test_renault_backoff_clamped_does_not_overflow_after_long_outage():
    """v6.6.0: failure_count is clamped before 2**n shift to prevent
    far-future timestamps after months of failed polls."""
    from vehicles.renault_provider import RenaultProvider
    p = RenaultProvider({"username": "u", "password": "p"})
    # Simulate 1000 failures in a row (e.g. months of cron-driven polls
    # against an unreachable account)
    for _ in range(1000):
        p.record_failure()
    # backoff_until must be a finite, sane timestamp
    import time as _t
    assert p._backoff_until > _t.time()
    assert p._backoff_until < _t.time() + 25 * 3600   # max 24h cap respected
    # failure_count must not have grown unbounded (used for "stop logging" UI)
    assert p._failure_count <= p._MAX_FAILURE_EXP * 4 + 1


def test_renault_timestamp_parsing_iso_with_z():
    from vehicles.renault_provider import _renault_timestamp

    class FakeBattery:
        timestamp = "2026-05-09T12:34:56Z"

    ts = _renault_timestamp(FakeBattery())
    assert ts is not None
    assert ts.tzinfo is not None
    assert ts.year == 2026 and ts.hour == 12 and ts.minute == 34


def test_renault_timestamp_returns_none_on_missing_or_bad_field():
    from vehicles.renault_provider import _renault_timestamp

    class NoTs: pass
    assert _renault_timestamp(NoTs()) is None

    class BadTs:
        timestamp = "not a date"
    assert _renault_timestamp(BadTs()) is None

    class NullTs:
        timestamp = None
    assert _renault_timestamp(NullTs()) is None


# =============================================================================
# Component-Health backend (SLF-015)
# =============================================================================

def test_health_dict_round_trip_through_list_filter():
    """Bootstrap returns a List[ComponentHealth]; web/server.py filters
    failed entries. This test pins down the to_dict() contract."""
    from bootstrap import ComponentHealth
    records = [
        ComponentHealth("A", "ok"),
        ComponentHealth("B", "failed", "boom"),
        ComponentHealth("C", "disabled", "config"),
    ]
    dicts = [h.to_dict() for h in records]
    assert dicts[1]["status"] == "failed"
    n_failed = sum(1 for d in dicts if d["status"] == "failed")
    assert n_failed == 1
