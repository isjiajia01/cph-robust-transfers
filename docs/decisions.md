# Decisions & Assumptions (living)

## Assumptions

- The repo should remain a hybrid software + research project.
- Existing runtime code paths in `src/` and automation in `infra/` are the source of truth.
- Template alignment should happen through documentation structure first, not disruptive code moves.

## Decisions

- [2026-03-15] Decision: Add a dedicated accessibility-product scaffold instead of extending the research dashboard into a full map app.
  Rationale: The target product is a quota-aware, map-first interaction model with provider proxying, cache rules, and frontend state management that does not fit cleanly inside the research dashboard path.
  Impact: Added `docs/accessibility_product_plan.md`, `src/accessibility/`, `web/accessibility/`, `configs/accessibility.defaults.toml`, and `data/cache/accessibility/` as the new product scaffold.

- [2026-03-15] Decision: Implement the first local accessibility proxy slice before validating live Labs traffic.
  Rationale: The repo can already support a real local server, cache keys, static map frontend, and overlay payloads even before a working Labs key is available in the environment.
  Impact: `src.accessibility.server` now serves static frontend assets plus `/api/health`, `/api/frontend-config`, `/api/station-overlays`, `/api/location-search`, and `/api/reachability`; live upstream calls still depend on `REJSEPLANEN_API_KEY`.

- [2026-03-15] Decision: Add a static HTML dashboard renderer for Week1-Week3 research outputs.
  Rationale: The repo already had reproducible figures, markdown summaries, and CSV tables, but no single view suitable for quick offline review or demo use.
  Impact: `src.app.results_dashboard` now generates `docs/research_dashboard.html` from committed artifacts without requiring a web server.

- [2026-03-15] Decision: Upgrade the research dashboard to a company-facing interactive format.
  Rationale: The first version was useful as a stitched report, but business review needs line filtering, a clearer executive summary, and a spatial view of exposure.
  Impact: `docs/research_dashboard.html` now presents executive KPI cards, client-side line filtering, and an offline GTFS-derived map of hubs and vulnerable nodes.

- [2026-03-06] Decision: Keep Cloud Run jobs deployed but pause scheduler triggers after sufficient data was collected.
  Rationale: Preserve manual re-run capability while stopping new Rejseplanen pulls.
  Impact: No automatic collection runs until the scheduler is resumed.

- [2026-03-06] Decision: Append collector outputs directly into BigQuery after each run.
  Rationale: GCS uploads alone were insufficient because downstream warehouse refresh was not continuous.
  Impact: `run_metrics`, `observations`, `departures`, `journey_stops`, and `api_errors` now update per collector run.

- [2026-03-06] Decision: Align the repo to the hybrid template through documentation scaffolding instead of renaming the production code layout.
  Rationale: The project already has working code, infra scripts, and data paths.
  Impact: Added top-level template docs (`AGENTS.md`, `codex.md`, `problem.md`, `experiments.md`, `model/`, `docs/workflow/`) while preserving the current runtime structure.

- [2026-03-06] Decision: Use `docs/next_phase_plan.md` as the canonical next-phase document.
  Rationale: The project needs one explicit source of truth for A->B->C->D execution order, defaults, test scope, and rollout assumptions.
  Impact: Supporting markdown files should summarize or reference the plan instead of drifting into parallel versions.

- [2026-03-06] Decision: Keep deterministic `run_id`, add `ingest_ts_utc` and `sampling_target_version`, and preserve request-level evidence (`request_id`, `is_retry_final`) as default engineering standards.
  Rationale: Coverage, gap attribution, and replayability depend on stable run identity and evidence columns.
  Impact: Schema evolution and reporting must preserve attribution and idempotency.

- [2026-03-06] Decision: Default `RiskModel` remains mode-level with explicit fallback thresholds before finer-grained models are attempted.
  Rationale: Current sample size supports a more explainable fallback chain better than aggressive line-level ranking.
  Impact: Router and future experiments must depend on the interface, not on raw BigQuery tables.
