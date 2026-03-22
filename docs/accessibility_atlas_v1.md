# Copenhagen Mobility Resilience Atlas V1

## Scope

This public atlas slice is intentionally constrained:

- Greater Copenhagen only, using an operational commuting boundary on the Denmark side.
- Fixed origin grid only.
- Three destination families only: `campus`, `hospital`, `job_hub`.
- Four fixed departure scenarios:
  - `2026-03-17T08:00`
  - `2026-03-17T11:00`
  - `2026-03-17T17:00`
  - `2026-03-21T12:00`
- Three thresholds only: `30`, `45`, `60` minutes.
- Transfer caps only: `1` and `2`.
- Frontend reads precomputed static files from `web/accessibility/data`.

## Build commands

Build the atlas bundle:

```bash
python3 -m src.accessibility.server build-atlas --config configs/accessibility.defaults.toml
```

Build the live API-backed atlas bundle:

```bash
REJSEPLANEN_API_KEY=... python3 -m src.accessibility.server build-atlas --config configs/accessibility.live.toml
```

Validate static assets after a build:

```bash
python3 -m src.accessibility.server build-static --out-dir web/accessibility
```

## Config

Default configuration lives in [configs/accessibility.defaults.toml](/Users/zhangjiajia/Library/Mobile%20Documents/com~apple~CloudDocs/Life%20OS/10-19%20Personal/11_Project/11.01cph-robust-transfers/configs/accessibility.defaults.toml).

Key atlas fields:

- `source_mode = "sample"` for deterministic offline demo data.
- `source_mode = "api"` to call Rejseplanen `/reachability` using the configured `REJSEPLANEN_API_KEY`.
- `origins_path`, `pois_path`, `scenarios_path` define the fixed V1 universe.
- `output_dir` points to the static bundle consumed by the frontend.
- live mode defaults to `forward=1` and `filterEndWalks=1` to keep the atlas aligned with forward accessibility queries and stricter last-leg realism.

## Data outputs

The build writes:

- [web/accessibility/data/atlas_bootstrap.json](/Users/zhangjiajia/Library/Mobile%20Documents/com~apple~CloudDocs/Life%20OS/10-19%20Personal/11_Project/11.01cph-robust-transfers/web/accessibility/data/atlas_bootstrap.json)
- `24` layer files under [web/accessibility/data/layers](/Users/zhangjiajia/Library/Mobile%20Documents/com~apple~CloudDocs/Life%20OS/10-19%20Personal/11_Project/11.01cph-robust-transfers/web/accessibility/data/layers)
- one per-origin detail file under [web/accessibility/data/origins](/Users/zhangjiajia/Library/Mobile%20Documents/com~apple~CloudDocs/Life%20OS/10-19%20Personal/11_Project/11.01cph-robust-transfers/web/accessibility/data/origins)

Each layer file contains a polygon feature per origin with category-specific metrics:

- reachable count
- weighted access score
- nearest travel time
- delta vs layer median
- percentile in the current layer

Each origin detail file contains:

- origin metadata
- metrics by scenario, threshold, and transfer cap
- prefiltered opportunity rows for POI rendering

## Live mode notes

When `source_mode = "api"`, the builder:

- calls `/reachability` only at the largest configured duration
- derives the `30/45/60` slices from returned stop travel times
- caches raw reachability results under `data/cache/accessibility`

That means the live precompute budget is:

- `origins x scenarios x max_change_options`

not:

- `origins x scenarios x durations x max_change_options`

So a `400 x 4 x 2` atlas build is `3,200` reachability calls before cache reuse.

The live build cannot run without `accessId`. I verified this against the public endpoint: requests without `accessId` return `Missing value for required param accessId`.

## Schema

The database schema draft is in [configs/sql/accessibility_atlas_schema.sql](/Users/zhangjiajia/Library/Mobile%20Documents/com~apple~CloudDocs/Life%20OS/10-19%20Personal/11_Project/11.01cph-robust-transfers/configs/sql/accessibility_atlas_schema.sql).
