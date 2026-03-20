# Architecture

## Data flow
1. GTFS static zip is downloaded and versioned under `data/gtfs/raw/`.
2. GTFS tables are extracted to `data/gtfs/parsed/<version>/`.
3. Stop-level graph and metrics are generated under `data/graph/<version>/`.
4. Realtime collector polls `multiDepartureBoard` and `journeyDetail`.
5. Raw payloads are append-only NDJSON in `data/realtime_raw/dt=YYYY-MM-DD/`.
6. Structured tables are emitted to `data/structured/dt=YYYY-MM-DD/`.

## Key constraints
- Internal long-lived IDs are GTFS IDs (`stop_id`, `trip_id`, `route_id`).
- API references are treated as short-lived join hints.
- API key is read from environment variable `REJSEPLANEN_API_KEY`.

## Reliability defaults
- Request timeout: 15s
- Max retries: 5
- Exponential backoff with jitter
- Token-bucket request limiting in collector
