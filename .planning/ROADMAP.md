# Roadmap: SmartLoad v6

## Milestones

- [x] **v1.0 MVP** -- Phases 1-8.1 (shipped 2026-02-24)
- [x] **v1.1 Smart EV Charging & evcc Control** -- Phases 9-12 (shipped 2026-02-27)
- [ ] **v1.2 Bugfixes** -- Phases 13-16 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-8.1) -- SHIPPED 2026-02-24</summary>

- [x] Phase 1: State Infrastructure (2/2 plans) -- completed 2026-02-22
- [x] Phase 2: Vehicle Reliability (2/2 plans) -- completed 2026-02-22
- [x] Phase 3: Data Foundation (3/3 plans) -- completed 2026-02-22
- [x] Phase 4: Predictive Planner (3/3 plans) -- completed 2026-02-22
- [x] Phase 4.1: Deploy Configuration (1/1 plan) -- completed 2026-02-22
- [x] Phase 4.2: CI/CD Pipeline (1/1 plan) -- completed 2026-02-23
- [x] Phase 4.3: Release Documentation (1/1 plan) -- completed 2026-02-23
- [x] Phase 5: Dynamic Buffer (2/2 plans) -- completed 2026-02-23
- [x] Phase 6: Decision Transparency (3/3 plans) -- completed 2026-02-23
- [x] Phase 7: Driver Interaction (3/3 plans) -- completed 2026-02-23
- [x] Phase 8: Residual RL and Learning (5/5 plans) -- completed 2026-02-23
- [x] Phase 8.1: Seasonal Feedback + Phase 5 Verification (1/1 plan) -- completed 2026-02-24

Full details: `milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>v1.1 Smart EV Charging & evcc Control (Phases 9-12) -- SHIPPED 2026-02-27</summary>

- [x] Phase 9: Vehicle SoC Provider Fix (2/2 plans) -- completed 2026-02-27
- [x] Phase 10: Poll Now Button + SoC Dashboard (2/2 plans) -- completed 2026-02-27
- [x] Phase 11: evcc Mode Control + Override Detection (2/2 plans) -- completed 2026-02-27
- [x] Phase 12: LP-Gated Battery Arbitrage (2/2 plans) -- completed 2026-02-27

Full details: `milestones/v1.1-ROADMAP.md`

</details>

### v1.2 Bugfixes (In Progress)

**Milestone Goal:** Fix all known production bugs -- PV forecast accuracy, evcc integration conflicts, vehicle data reliability, charge sequencer timing.

- [x] **Phase 13: PV Forecast & evcc Coexistence** - Fix PV forecast 2x factor and prevent SmartLoad from disrupting evcc PV surplus mode (completed 2026-03-08)
- [x] **Phase 14: Vehicle Data Reliability** - Fix vehicle polling, stale detection, and ManualSoC race condition (completed 2026-03-08)
- [x] **Phase 15: Charge Sequencer Transition** - Fix multi-vehicle queue delay on vehicle completion (completed 2026-03-08)
- [x] **Phase 16: EVCC-02 Gap Closure** - Fix departure urgency path and add "defers to evcc" decision log (completed 2026-03-08)

## Phase Details

### Phase 13: PV Forecast & evcc Coexistence
**Goal**: SmartLoad's PV forecast matches evcc reality and SmartLoad interventions coexist cleanly with evcc PV surplus charging
**Depends on**: Nothing (independent bugfix cluster)
**Requirements**: PVFC-01, EVCC-01, EVCC-02
**Success Criteria** (what must be TRUE):
  1. PV forecast values in SmartLoad match evcc solar tariff values within 5% -- no systematic 2x deviation visible in dashboard or logs
  2. When evcc is in PV surplus mode and a vehicle is charging from solar, SmartLoad does not lock the battery or switch modes unnecessarily
  3. SmartLoad only sends mode changes or battery lock commands when its LP plan requires an active intervention -- idle periods produce zero evcc API calls beyond status reads
  4. User can observe in the dashboard decision log that SmartLoad explicitly defers to evcc during PV surplus periods
**Plans**: 2 plans

Plans:
- [x] 13-01-PLAN.md -- Fix PV forecast 2x deviation with date-filtered solar summation
- [x] 13-02-PLAN.md -- Add command deduplication and transition-only arbitrage deactivation

---

### Phase 14: Vehicle Data Reliability
**Goal**: Vehicle SoC data is always correct and current -- polling works, stale detection accounts for wallbox connections, manual overrides survive concurrent updates
**Depends on**: Nothing (independent bugfix cluster)
**Requirements**: VHCL-01, VHCL-02, DATA-01
**Success Criteria** (what must be TRUE):
  1. Vehicle polling fetches current SoC from Kia Connect and Renault APIs without silent failures or stuck stale values
  2. A vehicle connected to the wallbox shows fresh SoC (not stale) when evcc websocket delivers live charging updates
  3. When a user sets ManualSoC via dashboard and an API poll runs concurrently, the manual value is preserved until the next successful API poll delivers genuinely newer data
  4. Dashboard vehicle cards display correct stale/fresh indicators matching actual data age
**Plans**: 2 plans

Plans:
- [x] 14-01-PLAN.md -- Fix poll_vehicle() merge and unify stale detection
- [x] 14-02-PLAN.md -- Fix ManualSoC race condition with timestamp-aware auto-clear

---

### Phase 15: Charge Sequencer Transition
**Goal**: Multi-vehicle charge queue transitions happen immediately when one vehicle completes charging
**Depends on**: Nothing (independent bugfix cluster)
**Requirements**: CHRG-01
**Success Criteria** (what must be TRUE):
  1. When vehicle A finishes charging, vehicle B (next in queue) receives its charge command within one decision cycle (max 15 minutes), not after an additional cycle delay
  2. The charge sequencer log shows the transition event with timestamps proving immediate handoff
**Plans**: 1 plan

Plans:
- [x] 15-01-PLAN.md -- TDD fix for _assign_time_windows current-hour-first and transition logging

---

### Phase 16: EVCC-02 Gap Closure
**Goal**: Fix departure urgency path (AttributeError at main.py:556) and add "defers to evcc" decision log visibility during PV surplus idle periods
**Depends on**: Nothing (fixes integration bug + cosmetic gap from Phase 13)
**Requirements**: EVCC-02
**Gap Closure**: Closes gaps from v1.2 milestone audit
**Success Criteria** (what must be TRUE):
  1. departure_store.get() is called correctly at main.py:556 -- departure urgency reaches mode controller
  2. When SmartLoad defers to evcc during PV surplus, the dashboard decision log shows "SmartLoad defers to evcc"
  3. Departure-based "now" mode activates when departure is imminent (departure_urgent=True reaches mode controller)
**Plans**: 1 plan

Plans:
- [ ] 16-01-PLAN.md -- TDD fix departure_store bug + defers-to-evcc decision log entry

---

## Progress

**Execution Order:** 13 -> 14 -> 15 -> 16

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. State Infrastructure | v1.0 | 2/2 | Complete | 2026-02-22 |
| 2. Vehicle Reliability | v1.0 | 2/2 | Complete | 2026-02-22 |
| 3. Data Foundation | v1.0 | 3/3 | Complete | 2026-02-22 |
| 4. Predictive Planner | v1.0 | 3/3 | Complete | 2026-02-22 |
| 4.1 Deploy Configuration | v1.0 | 1/1 | Complete | 2026-02-22 |
| 4.2 CI/CD Pipeline | v1.0 | 1/1 | Complete | 2026-02-23 |
| 4.3 Release Documentation | v1.0 | 1/1 | Complete | 2026-02-23 |
| 5. Dynamic Buffer | v1.0 | 2/2 | Complete | 2026-02-23 |
| 6. Decision Transparency | v1.0 | 3/3 | Complete | 2026-02-23 |
| 7. Driver Interaction | v1.0 | 3/3 | Complete | 2026-02-23 |
| 8. Residual RL and Learning | v1.0 | 5/5 | Complete | 2026-02-23 |
| 8.1 Seasonal Feedback | v1.0 | 1/1 | Complete | 2026-02-24 |
| 9. Vehicle SoC Provider Fix | v1.1 | 2/2 | Complete | 2026-02-27 |
| 10. Poll Now Button + SoC Dashboard | v1.1 | 2/2 | Complete | 2026-02-27 |
| 11. evcc Mode Control + Override Detection | v1.1 | 2/2 | Complete | 2026-02-27 |
| 12. LP-Gated Battery Arbitrage | v1.1 | 2/2 | Complete | 2026-02-27 |
| 13. PV Forecast & evcc Coexistence | v1.2 | 2/2 | Complete | 2026-03-08 |
| 14. Vehicle Data Reliability | v1.2 | 2/2 | Complete | 2026-03-08 |
| 15. Charge Sequencer Transition | v1.2 | 1/1 | Complete | 2026-03-08 |
| 16. EVCC-02 Gap Closure | 1/1 | Complete   | 2026-03-08 | - |
