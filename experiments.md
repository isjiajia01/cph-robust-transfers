# Experiments

Use this file to store reproducible analysis milestones.

## Next Execution Order

- A: sampling-system engineering and evidence chain
- B: static GTFS OR result hardening
- C: replaceable robust-transfer risk model and router
- D: uncertainty expression and shrinkage

Primary reference: `docs/next_phase_plan.md`

## Week 1 Baseline

- date: 2026-03-02
- scope: GTFS -> parsed feed -> stop graph -> baseline metrics
- dataset: `data/gtfs/raw/gtfs_20260302T085705Z.zip`
- outputs:
  - `data/graph/20260302/edges.csv`
  - `data/graph/20260302/nodes.csv`
  - `data/graph/20260302/metrics.csv`
- key metrics:
  - stops: `36,871`
  - directed edges: `50,141`
  - largest component ratio: `60.60%`

notes:
- baseline established the static network for downstream robustness work

## Week 2 Robustness

- date: 2026-03-02
- model: targeted vs random node removal
- dataset: `data/graph/20260302/*`
- outputs:
  - `data/robustness/20260302_enhanced/robustness_runs.csv`
  - `data/robustness/20260302_enhanced/robustness_summary.csv`
- key metrics:
  - targeted removals degrade LCC faster than random removals
  - extra metrics tracked: reachable OD ratio, avg shortest path

notes:
- targeting rule used approximate betweenness

## Week 3 Realtime Recovery

- date: 2026-03-06
- scope: restore BigQuery ingestion and backfill 2026-03-02..2026-03-06
- infra:
  - collector image `realtime-collector:20260306-192636`
  - scheduler state: paused after data sufficiency was reached
- key metrics:
  - 24h run coverage: `480/481` (`0.9979`)
  - critical gaps: `0`
  - error_429_ratio: `0.0`

notes:
- direct collector-to-BigQuery append was added after GCS-only operation left the warehouse stale

next action:
- execute A in full against the schema, task orchestration, and summary contract defined in `docs/next_phase_plan.md`

## Research Dashboard

- date: 2026-03-15
- scope: render an offline HTML view across Week1 static metrics, Week2 robustness, and Week3 reliability/risk artifacts
- inputs:
  - `docs/week1_summary.md`
  - `results/robustness/summary.md`
  - `data/analysis/reports/week3/dt=2026-03-02/summary.json`
  - `data/analysis/week3_line_reliability_rank.csv`
  - `data/analysis/week3_hour_dow_quantiles.csv`
  - `data/analysis/router_pareto_table.csv`
  - `data/analysis/risk_model_mode_level.csv`
- outputs:
  - `src/app/results_dashboard.py`
  - `docs/research_dashboard.html`
- checks:
  - `python3 -m unittest tests.test_results_dashboard tests.test_template_cli`
  - `python3 -m src.app.results_dashboard --out docs/research_dashboard.html`

notes:
- dashboard is intentionally self-contained and opens from disk without a local web server

## Accessibility Product Scaffold

- date: 2026-03-15
- scope: formalize a quota-aware map-first accessibility product plan and create repo scaffolding for the future proxy/frontend implementation
- outputs:
  - `docs/accessibility_product_plan.md`
  - `src/accessibility/`
  - `web/accessibility/`
  - `configs/accessibility.defaults.toml`
  - `data/cache/accessibility/README.md`
- checks:
  - `python3 -m unittest tests.test_accessibility_scaffold`

notes:
- scaffold intentionally avoids wiring live Labs calls until access and response validation are available

## Accessibility Phase 2 Local Proxy

- date: 2026-03-15
- scope: turn the accessibility scaffold into a real local proxy + cache + map frontend slice
- outputs:
  - `src/accessibility/server.py`
  - `src/accessibility/rejseplanen_client.py`
  - `src/accessibility/cache.py`
  - `src/accessibility/transform.py`
  - `web/accessibility/index.html`
  - `web/accessibility/app.js`
  - `web/accessibility/styles.css`
  - `src/app/accessibility_pipeline.py`
- checks:
  - `python3 -m unittest tests.test_accessibility_scaffold tests.test_template_cli`
  - `python3 -m src.accessibility.server build-static`
  - local server smoke test on `127.0.0.1:8765` for `/api/health`, `/api/station-overlays`, and `/`

notes:
- upstream Rejseplanen calls are now wired through real endpoint/path config, but current environment does not include a Labs key
- `/api/location-search` returns an explicit missing-key error until `REJSEPLANEN_API_KEY` is set

## Accessibility Live Validation

- date: 2026-03-15
- scope: validate the local accessibility proxy against live Rejseplanen Labs responses using the existing GCP Secret Manager key
- live checks:
  - `location.name` WADL fetched and confirmed `input` + `maxNo`
  - `reachability` WADL fetched and confirmed `originId`, `date`, `time`, `duration`, `maxChange`, `products`
  - local `/api/location-search?q=Norreport&limit=3` returned normalized live items headed by `8600646`
  - local `/api/reachability` for `originId=8600646`, `2026-03-16T08:30`, `45 min`, `maxChange=2` returned `3832` normalized reachable stops
- code impacts:
  - reachability config switched from guessed `timeFrame` / `maxChg` to real `duration` / `maxChange`
  - mode filter now maps to a `products` bitmask for train / metro / bus
  - location normalization now prefers stable `extId`

notes:
- live validation used the existing secret `REJSEPLANEN_API_KEY` from GCP Secret Manager for project `cph-robust-transfers-260302`
- browser-level visual verification of the live map UI was not performed in this terminal-only session

## Accessibility UX Hardening

- date: 2026-03-16
- scope: add result clipping/pagination, cluster-based map rendering, and a more ranger-like map-first UI shell
- outputs:
  - paginated `/api/reachability` response with `map_stops`, `reachable_stops`, and page stats
  - Leaflet marker clustering plus travel-time bucket summary
  - floating overlay layout replacing the previous three-column document layout
- checks:
  - `python3 -m unittest tests.test_accessibility_scaffold tests.test_template_cli`
  - local live proxy smoke test confirmed `total=3832`, `clipped=1200`, `page=2/24`, `returned=50`

notes:
- map rendering now uses the clipped `map_stops` window while the list uses paginated `reachable_stops`
- browser-level acceptance used headless Chrome screenshots for both shell-only and live autorun states
- live filtered smoke test confirmed `sort=quality_desc`, `bucket=0-15`, `direct_only=true` returns `309` matching stops

## Accessibility Share Link + Compact Layout

- date: 2026-03-16
- scope: turn URL-prefill into a formal shareable-link flow and tighten the map UI for short/mobile viewports
- outputs:
  - share button now copies a full autorun URL with origin, filters, paging, and mode state
  - frontend syncs query state back into `window.history`
  - short viewport CSS compresses toolbar/panel spacing and allows panel scrolling instead of hard clipping
- checks:
  - `python3 -m unittest tests.test_accessibility_scaffold tests.test_template_cli`
  - headless Chrome screenshots captured after the compact-layout pass

notes:
- URL state now supports a reproducible autorun query instead of only passive prefill
- browser QA still shows the left panel is dense on 900px height, but it remains usable and scrollable rather than truncating

## Executive Dashboard Upgrade

- date: 2026-03-15
- scope: upgrade the offline dashboard for company-facing review with interactive filtering and spatial exposure view
- inputs:
  - `data/gtfs/parsed/20260302/stops.csv`
  - `results/robustness/top10_vulnerable_nodes.csv`
  - `data/analysis/week3_line_reliability_rank.csv`
  - `data/analysis/week3_hour_dow_quantiles.csv`
- outputs:
  - `docs/research_dashboard.html`
- checks:
  - `python3 -m unittest tests.test_results_dashboard tests.test_template_cli`
  - `python3 -m src.app.results_dashboard --out docs/research_dashboard.html`

notes:
- page remains offline and reproducible, but now includes line search, band filtering, and a GTFS-derived exposure map
