# Copenhagen Accessibility Product Plan

Date: 2026-03-15

## Goal

Define a quota-aware, map-first Copenhagen accessibility product that can grow from a Rejseplanen Labs MVP into a deeper routing/reliability product.

This plan assumes:

- first release is API-first rather than self-hosted timetable routing
- reachability is computed only on explicit user action
- the current repo remains the source of truth for reliability/risk overlays

## Product Scope

### Core user flow

1. User searches for an origin stop or place.
2. User chooses departure time, max travel time, mode filters, and max changes.
3. User clicks `Update map`.
4. Backend resolves a cached or live Rejseplanen reachability result.
5. Frontend renders reachable stops plus repo-derived reliability overlays.

### Out of scope for V1

- drag-to-recompute interaction
- continuously animated map updates
- self-hosted earliest-arrival engine
- fully continuous polygon/isochrone generation as a hard dependency
- account system or billing

## Information Architecture

Single-screen, map-first layout.

### 1. Top control bar

- origin search
- departure time selector
- max travel time slider
- mode filter chips / multi-select
- max changes selector
- primary `Update map` action

Rules:

- control changes do not trigger reachability automatically
- only the primary action triggers `/api/reachability`

### 2. Left results panel

- current query summary
- reachable stop count
- freshness indicator: `live`, `cache hit`, `stale cache`
- reliability summary by band
- stop list sorted by travel time
- short business-facing conclusion

### 3. Main map canvas

- Copenhagen-focused basemap
- reachable stop markers colored by travel-time bucket
- optional overlay toggles:
  - reliability band
  - top hubs
  - vulnerable nodes

### 4. Right detail panel

- selected stop name
- travel time and bucket
- matched line/mode information if available
- repo-derived reliability labels:
  - `p95 delay`
  - `confidence_tag`
  - `evidence_level`

## API Route Design

The frontend should never call Rejseplanen Labs directly. Use a thin local proxy layer.

### `GET /api/health`

Purpose:

- health probe
- reveal config state for local/dev environments

Response shape:

```json
{
  "ok": true,
  "has_labs_key": true,
  "cache_root": "data/cache/accessibility",
  "version": "v1"
}
```

### `GET /api/location-search?q=...&limit=8`

Purpose:

- proxy Rejseplanen `Location Search by Name`
- normalize candidate items for the frontend

Response shape:

```json
{
  "query": "norreport",
  "items": [
    {
      "id": "8600646",
      "name": "Nørreport St",
      "type": "stop",
      "lat": 55.683,
      "lon": 12.571
    }
  ],
  "cache": {
    "hit": true
  }
}
```

### `POST /api/reachability`

Purpose:

- compute reachability from explicit user input
- apply cache lookup before calling Rejseplanen Labs
- enrich reachable stops with repo reliability overlays

Request shape:

```json
{
  "origin": {
    "id": "8600646",
    "type": "stop"
  },
  "depart_at_local": "2026-03-16T08:30:00",
  "max_minutes": 45,
  "modes": ["train", "metro", "bus"],
  "max_changes": 2
}
```

Response shape:

```json
{
  "query": {
    "origin_id": "8600646",
    "depart_at_local": "2026-03-16T08:30:00",
    "time_bucket_local": "2026-03-16T08:30",
    "max_minutes": 45,
    "modes": ["bus", "metro", "train"],
    "max_changes": 2
  },
  "stats": {
    "reachable_stop_count": 128,
    "cache_status": "hit",
    "generated_at_utc": "2026-03-15T20:15:00Z"
  },
  "reachable_stops": [
    {
      "id": "8600626",
      "name": "København H",
      "lat": 55.672,
      "lon": 12.565,
      "travel_time_min": 11,
      "reliability_band": "stable",
      "risk_p95_delay_sec": 120,
      "confidence_tag": "medium"
    }
  ]
}
```

### `GET /api/station-overlays`

Purpose:

- provide static overlay layers derived from the repo
- avoid rebuilding hub/vulnerability payloads inside the frontend

Suggested payload:

- top hubs from Week1 summary
- vulnerable nodes from Week2 results bundle
- reliability lookup artifacts keyed by stop/line when available

## Cache Key Design

### Location search cache key

```text
location:v1:{normalized_query}:{limit}
```

### Reachability cache key

```text
reachability:v1:
origin={origin_key}:
date={service_date_local}:
time={time_bucket_5m}:
dur={max_minutes}:
modes={sorted_modes}:
changes={max_changes}
```

### Rules

- `origin_key`
  - use official stop/place id when present
  - otherwise round coordinates to fixed precision
- `service_date_local`
  - keep local date separate from time bucket
- `time_bucket_5m`
  - round down to 5-minute buckets by default
- `sorted_modes`
  - sort before joining to avoid duplicate logical keys
- prefix with `v1`
  - allows full-key invalidation when transform logic changes

### Suggested TTLs

- location search: `1d` to `7d`
- reachability: `15m` to `60m`
- station overlays: `7d`

### Cache layers

1. Memory LRU
   - hot responses
   - shortest TTL
2. Disk cache under `data/cache/accessibility/`
   - supports local development and stale-if-error fallback

## Frontend State Machine

State transitions should be explicit and quota-aware.

### States

- `idle`
- `editing_query`
- `resolving_origin`
- `ready_to_run`
- `loading_reachability`
- `results_ready`
- `stale_results`
- `error`

### Transition rules

- typing in search box can enter `resolving_origin`
- parameter edits enter `editing_query`
- only clicking `Update map` can enter `loading_reachability`
- map pan/zoom/hover never enter `loading_reachability`
- if cached data is returned after upstream failure, enter `stale_results`

### UX implications

- keep previous result on screen while loading
- show freshness labels rather than clearing the map
- always allow retry from `error`

## Quota-Friendly Interaction Rules

- no reachability recompute while typing
- no recompute on slider drag
- no recompute on map movement
- no background polling for accessibility results
- detail requests are lazy and user-initiated

## Repo Layout

### Backend proxy / transform layer

- `src/accessibility/__init__.py`
- `src/accessibility/rejseplanen_client.py`
- `src/accessibility/cache.py`
- `src/accessibility/transform.py`
- `src/accessibility/server.py`

### Frontend shell

- `web/accessibility/index.html`
- `web/accessibility/app.js`
- `web/accessibility/styles.css`

### Config and cache roots

- `configs/accessibility.defaults.toml`
- `data/cache/accessibility/README.md`

### Tests

- `tests/test_accessibility_scaffold.py`

## Delivery Phases

### Phase 1: scaffold

- add proxy module layout
- add config and cache conventions
- add static frontend shell
- add product plan doc

### Phase 2: location search

- wire `GET /api/location-search`
- normalize stop/place responses
- add query debounce and result selection in frontend

### Phase 3: reachability MVP

- wire `POST /api/reachability`
- add cache lookup
- render reachable stops on map
- show freshness and reachable count

### Phase 4: repo overlays

- join reachable stops with reliability/risk artifacts
- expose hub/vulnerable overlays
- add business-facing summaries

### Phase 5: product hardening

- request dedupe
- stale-if-error fallback
- shareable URLs
- logs/metrics for quota monitoring

## Open Unknowns

- exact `Reachability Search` response shape must be validated against a real Labs key
- polygon-like geometry should not be assumed until real responses confirm it
- final basemap/provider choice must be checked against licensing and branding needs
