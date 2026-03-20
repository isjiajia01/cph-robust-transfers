# AGENT.md - cph-robust-transfers

## 1) Project Purpose
This project builds a reproducible Copenhagen public transport robustness pipeline:
- Static GTFS ingest -> graph modeling -> robustness experiments (Week1-2).
- Realtime sampling from Rejseplanen API -> delay/risk analytics (Week3).
- Production-style data pipeline on GCP (Cloud Run + Scheduler + GCS + BigQuery).

Primary goal: quantify transfer robustness and disruption impact with both static network structure and realtime delay behavior.

## 2) AI Role in This Repo
Any AI agent working in this repo is expected to:
- Keep the data/analysis pipeline operational and reproducible.
- Prefer automation over manual one-off steps.
- Preserve existing architecture decisions unless intentionally replaced.
- Validate changes with runnable checks (script syntax/tests/smoke runs).
- Keep docs aligned with reality, especially this `agent.md`.

## 3) Current Architecture (Implemented)
- Realtime collector:
  - Endpoint: `multiDepartureBoard` + `journeyDetail`
  - Runtime: Cloud Run Job `cph-rt-collector`
  - Trigger: Cloud Scheduler every 3 minutes
- Storage:
  - Raw responses in GCS (`realtime_raw/...`)
  - Structured CSV outputs in GCS (`structured/...`)
- Warehouse:
  - BigQuery dataset: `cph_rt`
  - Tables: `departures`, `journey_stops`, `observations`, `api_errors`, `run_metrics`, `daily_summary`
- Local-time safety:
  - Enriched BQ views with Copenhagen timezone fields:
    - `departures_enriched`
    - `journey_stops_enriched`
    - `observations_enriched`
  - Fields include: `obs_ts_cph`, `hour_cph`, `dow_cph`
  - Daily Task A scheduler timezone: `Europe/Copenhagen`

## 4) GCP Wiring (Live)
Project:
- `cph-robust-transfers-260302`

Regions:
- Cloud Run: `europe-north1`
- Cloud Scheduler: `europe-west1` (Scheduler does not support `europe-north1` in this setup)

Buckets:
- Raw: `${PROJECT_ID}-cph-rt-raw`
- Structured: `${PROJECT_ID}-cph-rt-structured`

Service Accounts:
- `cph-rt-job@<project>.iam.gserviceaccount.com`
- `cph-rt-scheduler@<project>.iam.gserviceaccount.com`

Secrets:
- API key is stored in Secret Manager as `REJSEPLANEN_API_KEY`.
- Never commit secrets to repo.

## 5) Progress Status
Week1 done:
- GTFS download/versioning + parse + stop-level graph + baseline figures/notebook.

Week2 done:
- Random vs targeted robustness simulations.
- Targeted strategy uses betweenness.
- Added metrics: reachable OD ratio + avg shortest path.
- Figures/notebook updated.
- Week2 notebook is now auto-generated via `src.robustness.update_week2_notebook`.
- Week2 one-command runner is available: `infra/robustness/week2_run_all.sh` (sim -> report -> figures -> notebook).
- Phase B hardening completed on 2026-03-06:
  - `graph_manifest.json` schema upgraded with `data_date`, `node_count`, `edge_count`, and `filter_rules`
  - `critical_nodes_top10.csv` / `top10_vulnerable_nodes.csv` now include `planning_implication`
  - `results/robustness/summary.md` added as fixed narrative export
  - `results/robustness/graph_manifest.json` is now copied into the publishable results bundle
  - local static rerender completed from `data/graph/20260302` + `data/robustness/20260302_high`

Phase C implemented locally:
- Added explicit `RiskModel` interface contract in Python.
- Default `ModeLevelRiskModel` now follows `mode + hour_cph -> mode -> global`.
- Router assumptions moved to `configs/router.defaults.toml`.
- Pareto table output now carries `stop_type`, `source_level`, `delay_distribution`, and `context_json`.
- Local offline smoke run completed from `data/analysis/departures_recent_7d.csv` + `configs/od_candidates_sample.csv`.

Phase D implemented locally:
- Risk-model outputs now carry bootstrap CI fields, `uncertainty_note`, and shrinkage metadata.
- Router Pareto output now includes quantile point estimates, CI columns, and uncertainty notes.
- Task A summary assembly now supports `uncertainty` + top evidence rows when a local risk-model CSV is available.
- `render_week3_md_from_json.py` and `week3_conclusions.py` now render evidence level + interval text in markdown.
- Local offline smoke run completed against `/tmp/cph_phase_d/` outputs; no live sampling resumed.
- Offline research dashboard implemented on 2026-03-15:
  - `src.app.results_dashboard` renders `docs/research_dashboard.html`
  - dashboard combines Week1 static metrics, Week2 robustness bundle, and Week3 realtime/risk outputs
  - local render + tests succeeded with committed artifacts; no live collection resumed
- Company-facing dashboard upgrade implemented on 2026-03-15:
  - dashboard now includes executive KPI framing, client-side line filtering, and an offline GTFS-derived exposure map
  - line portfolio interactions are driven by committed CSV artifacts; no live API or external map tiles are required
  - local render + tests succeeded after the upgrade
- Accessibility product scaffold implemented on 2026-03-15:
  - added formal product plan in `docs/accessibility_product_plan.md`
  - added `src/accessibility/` proxy/cache/transform placeholder package
  - added `web/accessibility/` frontend shell and `configs/accessibility.defaults.toml`
  - added `data/cache/accessibility/` as the planned cache root
  - no live Rejseplanen Labs integration was enabled in this scaffold step
- Accessibility Phase 2 local slice implemented on 2026-03-15:
  - `src.accessibility.server` now serves the local map page and API routes
  - `src.accessibility.rejseplanen_client` builds real `location.name` / `reachability` requests from config
  - `src.accessibility.cache` now provides in-memory + disk JSON caching
  - `web/accessibility/` is now a Leaflet-based map page instead of a static placeholder
  - local smoke test passed for `/api/health`, `/api/station-overlays`, and static page delivery
  - live upstream search is still blocked until `REJSEPLANEN_API_KEY` is configured and the exact `reachability` payload shape is confirmed
- Accessibility live validation completed on 2026-03-15:
  - local proxy successfully queried live `location.name` and `reachability` using the Secret Manager key
  - `reachability` parameter names were corrected to `duration` + `maxChange`
  - mode filter now maps to the HAFAS `products` bitmask
  - live proxy query from Nørreport at `2026-03-16 08:30` with `45` minutes and `2` changes returned `3832` normalized reachable stops
  - remaining gap is UI-level refinement, not backend connectivity
- Accessibility UX hardening completed on 2026-03-16:
  - `/api/reachability` now returns a clipped `map_stops` window plus paginated `reachable_stops`
  - current default cap is `1200` map stops with paged list slices
  - frontend now uses marker clustering, travel-time bucket bars, and a floating map-first layout closer to the reference product
  - live smoke test confirmed paginated output: `3832` total, `1200` clipped, `50` rows on page `2/24`
  - added service-quality sorting/filtering controls and richer popup/detail explanations for line + transfer context
  - headless Chrome browser QA captured both shell and live autorun render states
  - live filtered smoke test confirmed `quality_desc + 0-15 bucket + direct_only` returns `309` matching stops
- Accessibility share-link and compact-layout pass completed on 2026-03-16:
  - URL state is now kept in sync with origin, filters, paging, and autorun-capable query params
  - share button copies a reproducible link rather than relying on manual URL edits
  - short viewport CSS now reduces toolbar density and allows overlay panels to scroll instead of clipping
  - browser QA via headless Chrome confirmed the updated shared-result view renders successfully at `1440x900`

Week3 in production:
- Realtime collector deployed; automatic schedule is currently paused.
- Delay fields parsed and persisted.
- Daily quality/report pipeline implemented.
- A-line observability upgrade implemented:
  - Deterministic `run_id` from scheduled minute (`YYYYMMDDTHHMM`)
  - `trigger_id`, `scheduled_ts_utc`, `job_start_ts_utc`, `job_end_ts_utc`, `ingest_ts_utc`
  - `sampling_target_version` (hash of stations/config), `collector_version` (env-injected)
  - `api_errors` table with `request_id` + `is_retry_final`
  - `run_gap_diagnostics` view with evidence columns and `rule_fired`
  - `daily_summary` table writing 1 row per run/day summary
- Latest collector redeploy completed on 2026-03-02 (image tag `realtime-collector:20260302-130249`).
- Manual Task A execution succeeded after redeploy (`cph-week3-data-quality-7nvjb`).
- Follow-up fix deployed on 2026-03-06 (image tag `realtime-collector:20260306-192636`) to append each collector run directly into BigQuery after GCS upload.
- Smoke test on 2026-03-06 restored BigQuery writes: latest `run_metrics` / `observations` / `departures` timestamps advanced to `2026-03-06 18:28:00 UTC`.
- Historical backfill from GCS to BigQuery was run on 2026-03-06 for `2026-03-02` through `2026-03-06`; run coverage by UTC date became `269, 480, 480, 480, 381` respectively.
- Acceptance metrics after backfill (queried 2026-03-06): 24h run coverage `0.9979` (`480/481`), critical gaps `0`, max gap `225s`, error_429_ratio `0.0`.
- Scheduler pause applied on 2026-03-06:
  - `cph-rt-collector-every-3min` -> `PAUSED`
  - `cph-week3-data-quality-daily` -> `PAUSED`
- Phase A is complete in code/docs/tests:
  - `observations` now carries `job_end_ts_utc` and `run_status`
  - Task A exports structured `gap_diagnostics`
  - markdown summary includes top gap diagnostics evidence
  - audit checklist is tracked in `docs/phase_a_gap_checklist.md`

## 6) Task A / Task B Split (Implemented)
Task A (GCP scheduled, data reliability layer):
- Cloud Run Job: `cph-week3-data-quality`
- Scheduler job: `cph-week3-data-quality-daily`
- Schedule: `20 2 * * *` with timezone `Europe/Copenhagen`
- Produces and uploads:
  - `gs://<REPORT_BUCKET>/reports/week3/dt=YYYY-MM-DD/summary.json`
  - `gs://<REPORT_BUCKET>/reports/week3/latest/summary.json`
  - plus quantiles/gap/integrity CSV + summary.md

Task B (Repo docs layer, suitable for GitHub Actions):
- Pulls `latest/summary.json` and renders `docs/week3_summary.md`.
- GitHub workflow template exists: `.github/workflows/week3-docs-update.yml`.
- Schedule is set to `40 1 * * *` UTC with concurrency guard.

## 7) Key Entry Points
Core scripts:
- `infra/gcp/bootstrap_project.sh`
- `infra/gcp/deploy_collector_job.sh`
- `infra/gcp/create_scheduler.sh`
- `infra/gcp/deploy_task_a_job.sh`
- `infra/gcp/create_scheduler_task_a.sh`
- `infra/gcp/setup_week3_alerts.sh`
- `infra/robustness/week2_run_all.sh`
- `infra/gcp/run_week3_alert_drill.sh`
- `infra/bigquery/check_week3_acceptance.sh`
- `infra/bigquery/snapshot_week3_status.sh`
- `infra/docs/configure_task_b_secrets.sh`
- `infra/bigquery/daily_week3_refresh.sh`
- `infra/bigquery/task_a_week3_data_quality.sh`
- `infra/docs/task_b_update_repo_docs.sh`

Core Python modules:
- `src/realtime/collector.py`
- `src/realtime/parser.py`
- `src/realtime/task_a_daily_job.py`
- `src/realtime/update_week3_summary.py`
- `src/realtime/render_week3_md_from_json.py`
- `src/robustness/update_week2_notebook.py`
- `src/app/results_dashboard.py`
- `src/accessibility/server.py`
- `src/accessibility/cache.py`
- `src/accessibility/rejseplanen_client.py`
- `src/accessibility/transform.py`
- `src/app/accessibility_pipeline.py`

## 8) Current Operational Expectation
- Collector Cloud Run job remains deployable and runnable, but automatic scheduler trigger is currently paused.
- Task A job remains deployable and runnable, but automatic daily scheduler trigger is currently paused.
- 24h completeness should be judged from `summary.json` fields:
  - `sampling_24h.coverage_ratio`
  - `sampling_24h.critical_gap_count`
  - `sampling_24h.max_gap_sec`
- Weekly conclusion artifacts are generated by `src/realtime/week3_conclusions.py`.
- Offline research dashboard is generated by `python3 -m src.app.results_dashboard --out docs/research_dashboard.html`.
- Current dashboard is suitable for company review decks and internal demos without adding a web backend.
- Accessibility product planning and scaffolding now live in `docs/accessibility_product_plan.md` plus `src/accessibility/` and `web/accessibility/`.
- Local accessibility app entry points now exist via `python3 -m src.accessibility.server serve` and `python3 -m src.app.cli accessibility-build-static`.
- Alert drill can be triggered via `infra/gcp/run_week3_alert_drill.sh` (created policy `CPH RT Alert Drill` and test log token `CPH_ALERT_DRILL_TOKEN_20260302T121854Z`).

## 9) Known Caveats
- Rejseplanen API usage is currently constrained; do not restart schedulers or realtime collector without explicit user confirmation.
- Early 24h windows can show low coverage if pipeline started recently.
- Some scripts may show non-blocking GCP environment-tag warnings.
- Do not interpret peak-hour results using UTC; use Copenhagen-derived fields.
- `collector_version` will be `unknown` until collector is redeployed from a git repo with a valid `HEAD`.
- Week3 coverage metrics are still ramping because the 24h window includes pre-start periods.
- Cloud Logging alerts rely on collector log signal; deploy collector image after code changes so `api_error_summary` is emitted.
- 24h acceptance is not expected to pass immediately after redeploy/start; use `infra/bigquery/check_week3_acceptance.sh` after enough wall-clock runtime.
- Current acceptance snapshot (2026-03-02 12:11 UTC): coverage `0.0644`, critical gaps `0`, error_429_ratio `0.0`; failure reason is only `coverage<0.9`.
- GitHub Task B cannot be fully activated from this local repo until a git remote exists; use `infra/docs/configure_task_b_secrets.sh` once repo slug is available.

## 10) Mandatory Maintenance Rule For Every AI Agent
Every AI agent must maintain this `agent.md` as part of normal work.

Required behavior:
- After any meaningful architecture/process/status change, update this file in the same session.
- Add new components, remove deprecated ones, and correct stale operational details.
- If uncertain, leave a short "Open item" note instead of silent drift.

Minimum update checklist per agent session:
- What changed?
- Why it changed?
- Current run/deploy state (if infra touched).
- What remains pending next?

If you changed code but did not update `agent.md`, the task is not complete.

## 11) Template Alignment Status
- As of 2026-03-06, the repo has been aligned to the `/Users/zhangjiajia/Life_OS/00-09 Core/02.00 Templates/hybrid-codex-template` information architecture.
- Added top-level control docs: `AGENTS.md`, `codex.md`, `problem.md`, `experiments.md`.
- Added template-style process docs: `docs/decisions.md`, `docs/literature.md`, `docs/workflow/`, and `model/`.
- Added physical bridge packages `src/app` and `src/optimization`, plus semantic data roots `data/raw` and `data/processed`.
- Added second-stage template entry points:
  - `src/app/cli.py`
  - `src/optimization/api.py`
  - `src/optimization/cli.py`
  - `data/processed/static/`
  - `data/processed/analysis/`
- Production runtime paths were still preserved; template alignment was done through bridge layers and mapping docs rather than disruptive directory renames.
- Canonical forward plan is now `docs/next_phase_plan.md`, and supporting markdown files were aligned to that A->B->C->D plan plus its engineering defaults.
- Phase A implementation status is captured in `docs/phase_a_gap_checklist.md`; current state is complete with no remaining code/test gaps against the Phase A plan.
- Phase B publishable outputs now live in `results/robustness/` with fixed file names and a markdown summary; remaining later-phase work should move to C/D unless the static graph needs deeper metadata enrichment.
- Phase C contract is now documented in `model/solver.md`; remaining later-phase work is mainly D (uncertainty/shrinkage hardening) plus any future upgrade from mode-level to line-level risk components.
- Phase D is now implemented in code/docs/tests for offline use; remaining future work is optional refinement of the shrinkage method if you later want a stricter Bayesian treatment.
