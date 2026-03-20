# Runbook

## Local pipeline

### Week 1: GTFS -> Graph
```bash
python -m src.gtfs_ingest.download --url "$GTFS_STATIC_URL" --out-dir data/gtfs/raw
python -m src.gtfs_ingest.parse --input data/gtfs/raw/<file>.zip --out data/gtfs/parsed/latest
python -m src.graph.build_stop_graph --gtfs-dir data/gtfs/parsed/latest --out data/graph/latest
python -m src.graph.metrics --edges data/graph/latest/edges.csv --out data/graph/latest/metrics.csv
```

### Week 2: Robustness
```bash
python -m src.robustness.simulate_failures --edges data/graph/latest/edges.csv --out data/robustness/latest
python -m src.robustness.report --input data/robustness/latest/robustness_runs.csv --out data/robustness/latest/robustness_summary.csv
python -m src.robustness.week2_report --runs data/robustness/latest/robustness_runs.csv --edges data/graph/latest/edges.csv --nodes data/graph/latest/nodes.csv --results-dir results/robustness
python -m src.robustness.update_week2_notebook --base-dir ../data/robustness/latest --out notebooks/02_robustness_experiments.ipynb
```

### Week 2: one-command pipeline (includes notebook refresh)
```bash
bash infra/robustness/week2_run_all.sh data/graph/20260302/edges.csv data/graph/20260302/nodes.csv data/robustness/20260302_high
```

### Week 3: Realtime one-shot
```bash
export REJSEPLANEN_API_KEY="<secret>"
export REJSEPLANEN_BASE_URL="https://www.rejseplanen.dk/api"
python -m src.realtime.collector --config configs/pipeline.defaults.toml --stations configs/stations_seed.csv --base-url "$REJSEPLANEN_BASE_URL" --once
```

## GCP deployment (project wired)

### 0) Set exact env
```bash
export PROJECT_ID="cph-robust-transfers-260302"
export REGION="europe-north1"
export SCHEDULER_REGION="europe-west1"
export REJSEPLANEN_BASE_URL="https://www.rejseplanen.dk/api"
```

### 1) Bootstrap project resources
```bash
bash infra/gcp/bootstrap_project.sh "$PROJECT_ID" "$REGION"
```

### 2) Put API key in Secret Manager
```bash
bash infra/gcp/setup_secret.sh "$PROJECT_ID"
```

### 3) Deploy Cloud Run Job
```bash
bash infra/gcp/deploy_collector_job.sh "$PROJECT_ID" "$REGION" "$REJSEPLANEN_BASE_URL"
```

### 4) Create Scheduler (every 3 min)
```bash
bash infra/gcp/create_scheduler.sh "$PROJECT_ID" "$REGION" "*/3 * * * *" "$SCHEDULER_REGION"
```

### 5) Manual trigger for smoke test
```bash
gcloud run jobs execute cph-rt-collector --region "$REGION" --project "$PROJECT_ID" --wait
```

### 6) One-command deploy (Week3)
```bash
bash infra/gcp/week3_deploy_all.sh "$PROJECT_ID" "$REGION" "$REJSEPLANEN_BASE_URL" "*/3 * * * *" "$SCHEDULER_REGION"
```

### 7) Cloud Logging alerts for `API_TOO_MANY_REQUESTS` / `API_QUOTA`
```bash
# Optional: inspect available notification channels first
gcloud beta monitoring channels list --project "$PROJECT_ID"

# Create or update log metrics + alert policies
# Arg2 optional: comma-separated notification channel resource names
bash infra/gcp/setup_week3_alerts.sh "$PROJECT_ID"
# Example with channel:
# bash infra/gcp/setup_week3_alerts.sh "$PROJECT_ID" "projects/${PROJECT_ID}/notificationChannels/1234567890"
```

### 8) Alert drill (end-to-end email path)
```bash
bash infra/gcp/run_week3_alert_drill.sh "$PROJECT_ID" "projects/${PROJECT_ID}/notificationChannels/<id>"
```

## BigQuery load + quantiles

### Load one date from GCS structured layer
```bash
bash infra/bigquery/load_structured.sh "$PROJECT_ID" cph_rt "${PROJECT_ID}-cph-rt-structured" "2026-03-02"
```

### Run quantile query in BigQuery
```bash
mkdir -p data/analysis
bash infra/bigquery/run_delay_quantiles.sh "$PROJECT_ID" cph_rt data/analysis/delay_quantiles_bq.csv
```

### 24h sampling integrity check (BigQuery observations)
```bash
bash infra/bigquery/check_sampling_integrity_24h.sh "$PROJECT_ID" cph_rt 180 data/analysis
```

### Add Copenhagen local-time features (obs_ts_cph/hour_cph/dow_cph)
```bash
bash infra/bigquery/create_cph_time_features.sh "$PROJECT_ID" cph_rt "$REGION"
```

### Daily Week3 refresh (load + quantiles + integrity + summary)
```bash
bash infra/bigquery/daily_week3_refresh.sh "$PROJECT_ID" cph_rt "${PROJECT_ID}-cph-rt-structured" "$REGION" 180
```

## Split Automation (Recommended)

### Task A (GCP scheduler): data products + quality checks + machine-readable reports
```bash
export REPORT_BUCKET="${PROJECT_ID}-cph-rt-raw"
bash infra/gcp/deploy_task_a_job.sh "$PROJECT_ID" "$REGION" cph_rt "$REPORT_BUCKET" "$REGION" 180 "Europe/Copenhagen"
bash infra/gcp/create_scheduler_task_a.sh "$PROJECT_ID" "$REGION" "20 2 * * *" "$SCHEDULER_REGION" "Europe/Copenhagen"
gcloud run jobs execute cph-week3-data-quality --region "$REGION" --project "$PROJECT_ID" --wait
```

Outputs:
- `gs://<REPORT_BUCKET>/reports/week3/dt=YYYY-MM-DD/summary.json`
- `gs://<REPORT_BUCKET>/reports/week3/latest/summary.json`

### Task B (GitHub Actions): update repo docs from latest report
```bash
export REPORT_BUCKET="${PROJECT_ID}-cph-rt-raw"
bash infra/docs/task_b_update_repo_docs.sh "$REPORT_BUCKET"
```

GitHub Actions template:
- `.github/workflows/week3-docs-update.yml`

### Local quantile script from one departures.csv
```bash
python -m src.realtime.delay_quantiles --input data/structured/dt=2026-03-02/run_id=<run_id>/departures.csv --out data/analysis/delay_quantiles.csv
```

### Week3 acceptance gate (coverage/gap/429)
```bash
bash infra/bigquery/check_week3_acceptance.sh "$PROJECT_ID" cph_rt europe-north1 0.90 0 0.05
```

### Week3 ops status snapshot (markdown)
```bash
bash infra/bigquery/snapshot_week3_status.sh "$PROJECT_ID" cph_rt europe-north1 docs/week3_ops_status.md
```

## Week3+ Algorithm Layer (Risk Model + Router)

### Build mode-level risk model with bootstrap CI
```bash
python -m src.robustness.risk_model \
  --departures data/analysis/departures_20260302T093647Z.csv \
  --out data/analysis/risk_model_mode_level.csv \
  --n-mode-hour-min 200 \
  --n-mode-min 500
```

### Evaluate robust-transfer candidates (Pareto-ready output table)
```bash
python -m src.robustness.router \
  --departures data/analysis/departures_20260302T093647Z.csv \
  --candidates configs/od_candidates_sample.csv \
  --out data/analysis/router_pareto_table.csv \
  --config configs/router.defaults.toml
```

## Week3 Conclusion Layer (BQ-based)

```bash
# Export recent departures from BigQuery
bq --project_id="$PROJECT_ID" --location=europe-north1 query --nouse_legacy_sql --format=csv \
  'SELECT obs_ts_utc, line, mode, planned_dep_ts, realtime_dep_ts
   FROM `'"$PROJECT_ID"'.cph_rt.departures`
   WHERE SAFE.TIMESTAMP(obs_ts_utc) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
     AND SAFE.TIMESTAMP(planned_dep_ts) IS NOT NULL
     AND SAFE.TIMESTAMP(realtime_dep_ts) IS NOT NULL' \
  > data/analysis/departures_recent_7d.csv

# Risk model + Pareto table
python -m src.robustness.risk_model --departures data/analysis/departures_recent_7d.csv --out data/analysis/risk_model_mode_level.csv --n-mode-hour-min 200 --n-mode-min 500
python -m src.robustness.router --departures data/analysis/departures_recent_7d.csv --candidates configs/od_candidates_sample.csv --out data/analysis/router_pareto_table.csv --config configs/router.defaults.toml

# Hour/DOW quantiles + line reliability ranking + markdown summary
python -m src.realtime.week3_conclusions \
  --project-id "$PROJECT_ID" \
  --dataset cph_rt \
  --bq-location europe-north1 \
  --days 7 \
  --min-line-n 3 \
  --out-md docs/week3_conclusions.md
```

Task B GitHub secrets/setup:
- `docs/task_b_github_setup.md`
- or one-command secret setup (requires repo slug):
```bash
bash infra/docs/configure_task_b_secrets.sh "<owner/repo>" "${PROJECT_ID}-cph-rt-raw" "<GCP_WIF_PROVIDER>" "<GCP_WIF_SA>"
```

## Offline Research Dashboard

```bash
python3 -m src.app.results_dashboard --out docs/research_dashboard.html
```

Inputs:
- `docs/week1_summary.md`
- `results/robustness/summary.md`
- `data/analysis/reports/week3/dt=2026-03-02/summary.json`
- `data/analysis/week3_line_reliability_rank.csv`
- `data/analysis/week3_hour_dow_quantiles.csv`
- `data/analysis/router_pareto_table.csv`
- `data/analysis/risk_model_mode_level.csv`
- `data/gtfs/parsed/20260302/stops.csv`

Features in the rendered page:
- executive KPI cards for company-facing review
- client-side line search and band filtering
- offline GTFS-derived map of top hubs and vulnerable nodes

## Accessibility Product Scaffold

```bash
python3 -m unittest tests.test_accessibility_scaffold
python3 -m src.accessibility.server serve
python3 -m src.accessibility.server build-static
```

Primary files:
- `docs/accessibility_product_plan.md`
- `configs/accessibility.defaults.toml`
- `src/accessibility/server.py`
- `web/accessibility/index.html`

Local verification:
- `curl -sS http://127.0.0.1:8765/api/health`
- `curl -sS http://127.0.0.1:8765/api/station-overlays`
