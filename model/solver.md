# Solver / Execution Design

## Analytical Engines

- graph analytics in Python
- CSV / notebook based experiments
- BigQuery aggregation for realtime reliability summaries

## Execution Modes

1. Local deterministic processing
   - GTFS parse
   - graph build
   - robustness simulation
2. Cloud-scheduled realtime sampling
   - Cloud Run Job collector
   - GCS raw + structured outputs
   - BigQuery append for warehouse freshness
3. Post-processing and reporting
   - Task A quality/report job
   - markdown and figure generation

## Template Entry Points

- Application CLI:
  - `python -m src.app.cli realtime-collector`
  - `python -m src.app.cli graph-build`
- Optimization CLI:
  - `python -m src.optimization.cli risk-model`
  - `python -m src.optimization.cli router`

## Phase C Contract

- `RiskModel` input contract:
  - `line`
  - `mode`
  - `hour_cph`
  - `stop_type`
  - `context`
- Default implementation:
  - `ModeLevelRiskModel`
  - empirical distribution on `mode + hour_cph`
  - fallback to `mode`
  - fallback to `global`
- Router assumptions are config-driven from `configs/router.defaults.toml`:
  - `slack_min`
  - `minimum_transfer_time_min`
  - `walk_time_assumption_min`
  - `missed_transfer_rule`
- Standard router output is Pareto-ready and includes:
  - `od_id`
  - `depart_ts_cph`
  - `path_id`
  - `travel_time_min`
  - `transfers`
  - `miss_prob`
  - `cvar95_min`
  - `evidence_level`
  - `sample_size_effective`
  - `risk_model_version`

## Operational Criteria

- collection health:
  - recent BigQuery timestamps advance
  - 24h coverage stays near the 3-minute target
- acceptance gate:
  - coverage `>= 0.90`
  - critical gaps `= 0`
  - error_429_ratio `<= 0.05`

## Rollout Defaults

1. Phase A:
   - grey run for 1 day
   - observe `api_errors` volume and `run_metrics` duration distribution
2. Phase B/C/D:
   - publish daily OR summary artifacts
   - review risk-model stability weekly
3. Cost guardrails:
   - quantiles read recent partitions only
   - gap/integrity focus on the last 24h
   - `journeyDetail` load stays sampling-budget aware

## Current State

- collector is deployable and manually runnable
- scheduler is paused by user request to stop new Rejseplanen pulls
- historical window `2026-03-02..2026-03-06` has been backfilled into BigQuery
- next execution target is codified in `docs/next_phase_plan.md`
