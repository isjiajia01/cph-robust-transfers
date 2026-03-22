# Copenhagen Mobility Resilience Atlas

![Repository homepage preview](docs/figures/repo_homepage.png)

This repository is the closed-down public product for a Greater Copenhagen transit resilience atlas.

The core question is simple: under realistic transfer caps, fixed departure windows, and non-trivial destination weights, which neighborhoods still keep useful access to campuses, hospitals, and job hubs?

## What is here

- A static-first atlas in `web/accessibility` with precomputed GeoJSON layers and origin detail bundles.
- Builders and local serving utilities in `src/accessibility`.
- Public dashboards in `src/app` for benchmark and research review.
- Configuration and sample data for rebuilding the published slice in `configs`.

## Product framing

This is not a door-to-door trip planner and it is not a full historical research monorepo anymore.

It is a constrained resilience instrument:

- fixed scenarios instead of free-text search
- capped transfers instead of optimistic path expansion
- weighted destination access instead of raw polygon coverage
- static bundles that can be published cheaply and inspected directly

## Supported Commands

Serve the public site:

```bash
python3 -m src.accessibility.server serve
```

The default landing page is `web/accessibility/index.html`, with the atlas at `web/accessibility/atlas.html`.

Build atlas data from the configured slice:

```bash
python3 -m src.accessibility.server build-atlas --config configs/accessibility.defaults.toml
```

Validate static assets:

```bash
python3 -m src.accessibility.server build-static --out-dir web/accessibility
```

Render the benchmark dashboard:

```bash
python3 -m src.app.benchmark_dashboard
```

Render the research review dashboard:

```bash
python3 -m src.app.results_dashboard
```

## Scope

The old GTFS ingestion, realtime collection, robustness pipeline, and cloud deployment layers have been removed from the active surface of this repository.

What remains is the reproducible public site:

- overview landing page
- atlas
- benchmark dashboard
- research review dashboard
