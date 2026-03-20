# Next Phase Plan

## Summary

The next phase is no longer framed as independent Week 1 / Week 2 / Week 3 extensions.

The repository now moves toward a single flagship deliverable:

**a reliability-adjusted accessibility map and benchmark suite for Copenhagen transit**

Execution order remains practical, but the work is grouped by value chain rather than by isolated weekly modules.

## 1. Evidence Chain Hardening

Goal:
- make all realtime and analysis outputs attributable, reproducible, and benchmark-ready

Focus:
- complete collector evidence tables and summary contracts
- standardize manifests and version metadata
- make all daily/warehouse outputs easy to trace to a run, model, and parameter set

Primary outputs:
- stable `summary.json` contract
- stable `api_errors` / `run_metrics` / diagnostics outputs
- reproducible run metadata for downstream evaluation

## 2. Benchmark Layer

Goal:
- compare meaningful routing and accessibility baselines instead of producing standalone artifacts

Required baselines:
- scheduled-only
- realtime snapshot
- robust / risk-aware

Required metrics:
- expected arrival time
- p90 / p95 arrival time
- missed-transfer rate
- regret
- reachable opportunities within T minutes
- accessibility loss

Primary outputs:
- benchmark tables under `results/benchmark/`
- benchmark summary markdown
- benchmark-ready inputs for dashboard and case-study material

## 3. Reliability-Aware Accessibility

Goal:
- turn risk outputs into the main product/research surface

Required views:
- scheduled accessibility
- reliability-adjusted accessibility
- accessibility loss

Required explanations:
- station vulnerability
- line reliability context
- sample size / evidence level
- route-level risk explanation

Primary outputs:
- map-ready accessibility API payloads
- accessibility summaries and comparison views
- reusable artifacts for the accessibility frontend

## 4. Route and Risk Integration

Goal:
- ensure routing outputs are driven by the current empirical risk model rather than staying isolated

Focus:
- keep the `RiskModel` contract stable
- preserve fallback from mode-hour -> mode -> global
- expose model version, fallback level, and confidence/evidence tags in outputs

Primary outputs:
- route-evaluation tables with evidence metadata
- consistent risk model contract shared by benchmark and accessibility layers

## 5. Presentation Layer

Goal:
- make the repository interview-demo ready for research / optimization roles

Primary outputs:
- polished README
- benchmark-facing static page or markdown view
- updated offline dashboard
- concise case-study style narrative in docs

## Current Defaults

- first-stage work should avoid large framework changes
- first-stage work should reuse existing collector, graph, robustness, and dashboard assets
- Copenhagen remains the only target geography
- product UX is secondary to benchmark and evidence quality
