---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Bugfixes
status: executing
stopped_at: Completed 16-01-PLAN.md (EVCC-02 gap closure)
last_updated: "2026-03-08T19:27:17.614Z"
last_activity: 2026-03-08 -- Completed 13-01 (PV forecast date filter) and 13-02 (evcc command dedup)
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 6
  completed_plans: 6
  percent: 90
---

---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Bugfixes
status: executing
stopped_at: Completed 13-01-PLAN.md (PV forecast date filter)
last_updated: "2026-03-08T18:01:41.973Z"
last_activity: 2026-03-08 -- Completed 13-01 (PV forecast date filter) and 13-02 (evcc command dedup)
progress:
  [█████████░] 90%
  completed_phases: 1
  total_plans: 2
  completed_plans: 2
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-08)

**Core value:** The system makes the economically best energy decision at every moment using all available information -- and the user understands why
**Current focus:** v1.2 Bugfixes -- Phase 13 executing

## Current Position

Phase: 13 of 15 (PV Forecast & evcc Coexistence)
Plan: 2 of 2 in current phase (13-01 and 13-02 complete)
Status: Phase 13 complete
Last activity: 2026-03-08 -- Completed 13-01 (PV forecast date filter) and 13-02 (evcc command dedup)

Progress: [###░░░░░░░] 33% -- v1.2 (1/3 phases complete)

## Performance Metrics

**Velocity (v1.0+v1.1):**
- Total plans completed: 35
- Timeline: v1.0 31 days, v1.1 3 days
- Commits: 240+ total

## Accumulated Context

### Decisions

All v1.0/v1.1 decisions logged in PROJECT.md Key Decisions table.

- [13-01] Date filtering uses Europe/Berlin timezone, applied at summation points only (LP planner unfiltered)
- [13-01] Coverage hours capped at 24 in PVForecaster._count_future_hours
- [13-02] Used last-sent value tracking for Controller.apply() dedup (matching evcc_mode_controller pattern)
- [13-02] Added _deactivate_if_active() helper for transition-only gate exits in battery_arbitrage
- [Phase 14]: poll_vehicle() merges via update_from_api() instead of replacing VehicleData object
- [Phase 14]: is_data_stale() wallbox check requires evcc/live data_source (not just connected)
- [Phase 14]: Removed ad-hoc wallbox stale check from server.py, unified into is_data_stale()
- [Phase 14]: Auto-clear uses strict > comparison (poll_time > manual_ts) for timestamp-aware manual SoC clearing
- [Phase 15]: Force current hour as first slot only for rank-0 vehicle; lower-priority vehicles keep price-optimized assignment
- [Phase 16]: Used source-code grep integration tests to verify main.py correctness

### Pending Todos

None for v1.2.

### Blockers/Concerns

- RL agent requires 30-day shadow mode observation before advisory mode promotion (started 2026-02-24)
- DynamicBufferCalc requires 14-day observation period before live buffer changes (started 2026-02-24)
- Vehicle SoC API providers (Kia, Renault) not delivering data reliably -- VHCL-01 addresses this

## Session Continuity

Last session: 2026-03-08T19:27:17.609Z
Stopped at: Completed 16-01-PLAN.md (EVCC-02 gap closure)
Resume file: None
Next: Phase 14 planning or execution
