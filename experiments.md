# Experiments

Use this file to store reproducible milestones that support the repository's main claim:

**transit accessibility should be evaluated under reliability, not only under schedule assumptions**

## Current Execution Order

- 1. Evidence-chain hardening
- 2. Benchmark layer
- 3. Reliability-adjusted accessibility
- 4. Presentation and demo surfaces

Primary reference: `docs/next_phase_plan.md`

## Static Network Baseline

- date: 2026-03-02
- scope: GTFS ingest -> parsed feed -> stop graph -> baseline metrics
- dataset:
  - `data/gtfs/raw/gtfs_20260302T085705Z.zip`
- outputs:
  - `data/graph/20260302/edges.csv`
  - `data/graph/20260302/nodes.csv`
  - `data/graph/20260302/metrics.csv`
- key metrics:
  - stops: `36,871`
  - directed edges: `50,141`
  - largest component ratio: `60.60%`

notes:
- establishes the static network used by all downstream reliability and accessibility work

## Robustness Baseline

- date: 2026-03-02
- scope: targeted vs random node-removal robustness analysis
- dataset:
  - `data/graph/20260302/*`
- outputs:
  - `data/robustness/20260302_enhanced/robustness_runs.csv`
  - `data/robustness/20260302_enhanced/robustness_summary.csv`
- key findings:
  - targeted removals degrade the largest connected component faster than random removals
  - extra metrics tracked reachable OD ratio and average shortest-path degradation

notes:
- this is the system-fragility baseline, not yet the final rider-facing accessibility benchmark

## Realtime Reliability Recovery

- date: 2026-03-06
- scope: restore BigQuery ingestion and backfill 2026-03-02..2026-03-06
- infra:
  - collector image `realtime-collector:20260306-192636`
  - scheduler state paused after sufficient backfill
- key metrics:
  - 24h run coverage: `480/481` (`0.9979`)
  - critical gaps: `0`
  - error_429_ratio: `0.0`

notes:
- realtime operations are stable enough to support benchmark-grade reliability products

## Research Dashboard

- date: 2026-03-15
- scope: render an offline dashboard across static, robustness, and reliability outputs
- outputs:
  - `src/app/results_dashboard.py`
  - `docs/research_dashboard.html`
- checks:
  - `python3 -m unittest tests.test_results_dashboard tests.test_template_cli`
  - `python3 -m src.app.results_dashboard --out docs/research_dashboard.html`

notes:
- dashboard is self-contained and designed as a decision-facing artifact, not only as a developer utility

## Accessibility Product Scaffold

- date: 2026-03-15
- scope: create the initial map-first accessibility scaffold
- outputs:
  - `docs/accessibility_product_plan.md`
  - `src/accessibility/`
  - `web/accessibility/`
  - `configs/accessibility.defaults.toml`
- checks:
  - `python3 -m unittest tests.test_accessibility_scaffold`

notes:
- this milestone creates the product surface that will later host reliability-adjusted accessibility views

## Accessibility Live Validation

- date: 2026-03-15
- scope: validate live Rejseplanen-backed proxy behavior
- live checks:
  - `location.name` and `reachability` endpoints validated against real response contracts
  - `/api/location-search` returned normalized items headed by `8600646`
  - `/api/reachability` for `originId=8600646`, `2026-03-16T08:30`, `45 min`, `maxChange=2` returned `3832` normalized reachable stops

notes:
- live map support exists, but the current project still needs a benchmark layer that compares scheduled and reliability-adjusted outputs

## Accessibility UX Hardening

- date: 2026-03-16
- scope: improve pagination, clustering, and map-first layout
- outputs:
  - clipped map payloads
  - paginated list payloads
  - improved shell layout
- checks:
  - `python3 -m unittest tests.test_accessibility_scaffold tests.test_template_cli`

notes:
- UX work is useful, but future effort should be driven by benchmarked reliability insights rather than by shell polish alone

## Next Missing Milestone

- name: reliability-adjusted accessibility benchmark
- required comparison:
  - scheduled-only
  - realtime snapshot
  - robust / risk-aware
- required outputs:
  - benchmark tables
  - accessibility loss summaries
  - map-ready scheduled vs robust comparison payloads
