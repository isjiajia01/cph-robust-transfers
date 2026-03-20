# Architecture

## North-Star Flow

The repository is organized around one end-to-end question:

**How does transit uncertainty change accessibility and route quality in Copenhagen?**

The system has four layers:

1. **Data foundation**
   GTFS static ingest, parsing, graph construction, and realtime collection
2. **Reliability modeling**
   empirical delay distributions, risk estimation, and disruption simulation
3. **Accessibility and routing evaluation**
   route comparison, missed-transfer risk, and accessibility-loss computation
4. **Decision-facing outputs**
   benchmark tables, markdown summaries, dashboard views, and the accessibility prototype

## Data Flow

1. GTFS static zip is downloaded and versioned under `data/gtfs/raw/`.
2. GTFS tables are extracted to `data/gtfs/parsed/<version>/`.
3. Stop-level graph and metrics are generated under `data/graph/<version>/`.
4. Realtime collector polls `multiDepartureBoard` and `journeyDetail`.
5. Raw payloads are append-only NDJSON in `data/realtime_raw/dt=YYYY-MM-DD/`.
6. Structured tables are emitted to `data/structured/dt=YYYY-MM-DD/`.
7. Structured outputs feed delay quantiles, risk-model artifacts, routing outputs, and summary products.
8. Accessibility views consume both static network structure and reliability outputs.

## System Layers

### Data Foundation

- `src/gtfs_ingest`
- `src/graph`
- `src/realtime`
- `configs/`
- `infra/gcp`
- `infra/bigquery`

This layer is responsible for versioned ingestion, graph build, structured observations, and warehouse refreshes.

### Reliability Modeling

- `src/robustness/risk_model.py`
- `src/robustness/simulate_failures.py`
- `src/robustness/router.py`
- `src/optimization/`

This layer converts observed or simulated transit behavior into route-quality and risk estimates.

### Accessibility and Routing

- `src/accessibility/`
- `src/app/accessibility_pipeline.py`
- `configs/accessibility.defaults.toml`
- `configs/router.defaults.toml`

This layer turns delay/risk estimates into rider-facing accessibility and route-comparison outputs.

### Decision-Facing Outputs

- `docs/research_dashboard.html`
- `docs/week*_summary.md`
- `results/robustness/`
- planned benchmark outputs under `results/benchmark/`

This layer makes the project demoable for research, product, and hiring contexts.

## Key Constraints

- Internal long-lived IDs are GTFS IDs such as `stop_id`, `trip_id`, and `route_id`.
- API references are treated as short-lived join hints.
- API key is read from environment variable `REJSEPLANEN_API_KEY`.
- All analytical outputs should be attributable to a concrete data and model version.

## Reliability Defaults

- Request timeout: 15s
- Max retries: 5
- Exponential backoff with jitter
- Token-bucket request limiting in collector
- Hierarchical fallback in risk estimation is preferred over fragile fine-grained estimates
