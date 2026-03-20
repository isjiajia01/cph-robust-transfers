#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> [BQ_LOCATION]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
BQ_LOCATION="${3:-europe-north1}"

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false <<SQL
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.departures_enriched\` AS
SELECT
  d.*,
  SAFE.TIMESTAMP(d.obs_ts_utc) AS obs_ts_utc_ts,
  DATETIME(SAFE.TIMESTAMP(d.obs_ts_utc), "Europe/Copenhagen") AS obs_ts_cph,
  EXTRACT(HOUR FROM DATETIME(SAFE.TIMESTAMP(d.obs_ts_utc), "Europe/Copenhagen")) AS hour_cph,
  EXTRACT(DAYOFWEEK FROM DATETIME(SAFE.TIMESTAMP(d.obs_ts_utc), "Europe/Copenhagen")) AS dow_cph
FROM \`${PROJECT_ID}.${DATASET}.departures\` d;
SQL

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false <<SQL
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.journey_stops_enriched\` AS
SELECT
  j.*,
  SAFE.TIMESTAMP(j.obs_ts_utc) AS obs_ts_utc_ts,
  DATETIME(SAFE.TIMESTAMP(j.obs_ts_utc), "Europe/Copenhagen") AS obs_ts_cph,
  EXTRACT(HOUR FROM DATETIME(SAFE.TIMESTAMP(j.obs_ts_utc), "Europe/Copenhagen")) AS hour_cph,
  EXTRACT(DAYOFWEEK FROM DATETIME(SAFE.TIMESTAMP(j.obs_ts_utc), "Europe/Copenhagen")) AS dow_cph
FROM \`${PROJECT_ID}.${DATASET}.journey_stops\` j;
SQL

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false <<SQL
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.observations_enriched\` AS
SELECT
  o.*,
  SAFE.TIMESTAMP(o.request_ts) AS obs_ts_utc_ts,
  DATETIME(SAFE.TIMESTAMP(o.request_ts), "Europe/Copenhagen") AS obs_ts_cph,
  EXTRACT(HOUR FROM DATETIME(SAFE.TIMESTAMP(o.request_ts), "Europe/Copenhagen")) AS hour_cph,
  EXTRACT(DAYOFWEEK FROM DATETIME(SAFE.TIMESTAMP(o.request_ts), "Europe/Copenhagen")) AS dow_cph
FROM \`${PROJECT_ID}.${DATASET}.observations\` o;
SQL

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false <<SQL
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.api_errors_enriched\` AS
SELECT
  e.*,
  SAFE.TIMESTAMP(e.obs_ts_utc) AS obs_ts_utc_ts,
  DATETIME(SAFE.TIMESTAMP(e.obs_ts_utc), "Europe/Copenhagen") AS obs_ts_cph,
  EXTRACT(HOUR FROM DATETIME(SAFE.TIMESTAMP(e.obs_ts_utc), "Europe/Copenhagen")) AS hour_cph,
  EXTRACT(DAYOFWEEK FROM DATETIME(SAFE.TIMESTAMP(e.obs_ts_utc), "Europe/Copenhagen")) AS dow_cph
FROM \`${PROJECT_ID}.${DATASET}.api_errors\` e;
SQL

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false <<SQL
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.run_metrics_enriched\` AS
SELECT
  r.*,
  SAFE.TIMESTAMP(r.scheduled_ts_utc) AS scheduled_ts_utc_ts,
  DATETIME(SAFE.TIMESTAMP(r.scheduled_ts_utc), "Europe/Copenhagen") AS scheduled_ts_cph,
  EXTRACT(HOUR FROM DATETIME(SAFE.TIMESTAMP(r.scheduled_ts_utc), "Europe/Copenhagen")) AS scheduled_hour_cph,
  EXTRACT(DAYOFWEEK FROM DATETIME(SAFE.TIMESTAMP(r.scheduled_ts_utc), "Europe/Copenhagen")) AS scheduled_dow_cph
FROM \`${PROJECT_ID}.${DATASET}.run_metrics\` r;
SQL

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false <<SQL
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.run_gap_diagnostics\` AS
WITH ordered AS (
  SELECT
    r.*,
    SAFE.TIMESTAMP(r.scheduled_ts_utc) AS scheduled_ts,
    SAFE.TIMESTAMP(r.job_start_ts_utc) AS job_start_ts,
    SAFE.TIMESTAMP(r.job_end_ts_utc) AS job_end_ts,
    LAG(SAFE.TIMESTAMP(r.scheduled_ts_utc)) OVER (ORDER BY SAFE.TIMESTAMP(r.scheduled_ts_utc)) AS prev_scheduled_ts
  FROM \`${PROJECT_ID}.${DATASET}.run_metrics\` r
),
err AS (
  SELECT
    run_id,
    COUNT(*) AS error_rows,
    COUNTIF(http_code = 429 OR error_code = 'API_TOO_MANY_REQUESTS' OR error_code = 'API_QUOTA') AS throttled_rows,
    ARRAY_AGG(error_code IGNORE NULLS ORDER BY error_code LIMIT 1)[SAFE_OFFSET(0)] AS dominant_error_code
  FROM \`${PROJECT_ID}.${DATASET}.api_errors\`
  GROUP BY run_id
)
SELECT
  o.run_id,
  o.trigger_id,
  o.scheduled_ts_utc,
  o.job_start_ts_utc,
  o.job_end_ts_utc,
  TIMESTAMP_DIFF(o.scheduled_ts, o.prev_scheduled_ts, SECOND) AS gap_sec,
  TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND) AS cold_start_proxy_sec,
  SAFE_DIVIDE(COALESCE(e.error_rows, 0), NULLIF(o.board_request_count + o.journey_request_count, 0)) AS api_error_ratio,
  COALESCE(e.dominant_error_code, 'NONE') AS dominant_error_code,
  o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64) AS run_overrun,
  ABS(TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND)) > 120 AS scheduler_miss_proxy,
  COALESCE(e.throttled_rows, 0) > 0 AS has_throttle_signal,
  CASE
    WHEN o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64) AND COALESCE(e.throttled_rows, 0) > 0
      THEN 'duration_overrun && throttle_signal'
    WHEN ABS(TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND)) > 120
      THEN 'scheduler_miss_proxy'
    WHEN o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64)
      THEN 'duration_overrun'
    WHEN COALESCE(e.throttled_rows, 0) > 0
      THEN 'throttle_signal'
    ELSE 'fallback_unknown'
  END AS rule_fired,
  CASE
    WHEN ABS(TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND)) > 120 THEN 'scheduler_miss'
    WHEN o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64) THEN 'run_overrun'
    WHEN COALESCE(e.throttled_rows, 0) > 0 THEN 'api_throttle'
    ELSE 'network_or_unknown'
  END AS likely_cause
FROM ordered o
LEFT JOIN err e USING (run_id);
SQL

echo "Created/updated views:"
echo "- ${PROJECT_ID}.${DATASET}.departures_enriched"
echo "- ${PROJECT_ID}.${DATASET}.journey_stops_enriched"
echo "- ${PROJECT_ID}.${DATASET}.observations_enriched"
echo "- ${PROJECT_ID}.${DATASET}.api_errors_enriched"
echo "- ${PROJECT_ID}.${DATASET}.run_metrics_enriched"
echo "- ${PROJECT_ID}.${DATASET}.run_gap_diagnostics"
