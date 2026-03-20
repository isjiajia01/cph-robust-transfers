#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> <INTERVAL_SEC> <OUT_DIR> [BQ_LOCATION]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
INTERVAL_SEC="$3"
OUT_DIR="$4"
BQ_LOCATION="${5:-europe-north1}"

mkdir -p "$OUT_DIR"
SUMMARY_CSV="${OUT_DIR}/sampling_integrity_24h.csv"
GAPS_CSV="${OUT_DIR}/sampling_gaps_24h.csv"
TABLE_REF="\`${PROJECT_ID}.${DATASET}.observations\`"

SUMMARY_QUERY=$(cat <<SQL
WITH runs AS (
  SELECT
    run_id,
    SAFE.TIMESTAMP(MIN(request_ts)) AS run_ts
  FROM ${TABLE_REF}
  GROUP BY run_id
),
windowed AS (
  SELECT run_id, run_ts
  FROM runs
  WHERE run_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    AND run_ts IS NOT NULL
),
ordered AS (
  SELECT
    run_id,
    run_ts,
    LAG(run_ts) OVER (ORDER BY run_ts) AS prev_run_ts
  FROM windowed
),
gaps AS (
  SELECT
    run_id,
    run_ts,
    prev_run_ts,
    TIMESTAMP_DIFF(run_ts, prev_run_ts, SECOND) AS gap_sec
  FROM ordered
  WHERE prev_run_ts IS NOT NULL
),
stats AS (
  SELECT
    COUNT(*) AS run_count_24h,
    MIN(run_ts) AS first_run_ts,
    MAX(run_ts) AS last_run_ts,
    CAST(${INTERVAL_SEC} AS INT64) AS expected_interval_sec,
    CAST(FLOOR(86400.0 / CAST(${INTERVAL_SEC} AS FLOAT64)) + 1 AS INT64) AS expected_runs_24h
  FROM windowed
),
gap_stats AS (
  SELECT
    COUNTIF(gap_sec > CAST(${INTERVAL_SEC} AS INT64) * 2) AS critical_gap_count,
    COUNTIF(gap_sec > CAST(${INTERVAL_SEC} AS INT64) * 1.5) AS warning_gap_count,
    MAX(gap_sec) AS max_gap_sec
  FROM gaps
)
SELECT
  run_count_24h,
  expected_runs_24h,
  SAFE_DIVIDE(run_count_24h, expected_runs_24h) AS run_coverage_ratio,
  expected_interval_sec,
  first_run_ts,
  last_run_ts,
  COALESCE(critical_gap_count, 0) AS critical_gap_count,
  COALESCE(warning_gap_count, 0) AS warning_gap_count,
  COALESCE(max_gap_sec, 0) AS max_gap_sec
FROM stats CROSS JOIN gap_stats
SQL
)

GAPS_QUERY=$(cat <<SQL
WITH runs AS (
  SELECT
    run_id,
    SAFE.TIMESTAMP(MIN(request_ts)) AS run_ts
  FROM ${TABLE_REF}
  GROUP BY run_id
),
windowed AS (
  SELECT run_id, run_ts
  FROM runs
  WHERE run_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    AND run_ts IS NOT NULL
),
ordered AS (
  SELECT
    run_id,
    run_ts,
    LAG(run_id) OVER (ORDER BY run_ts) AS prev_run_id,
    LAG(run_ts) OVER (ORDER BY run_ts) AS prev_run_ts
  FROM windowed
)
SELECT
  prev_run_id,
  prev_run_ts,
  run_id,
  run_ts,
  TIMESTAMP_DIFF(run_ts, prev_run_ts, SECOND) AS gap_sec
FROM ordered
WHERE prev_run_ts IS NOT NULL
  AND TIMESTAMP_DIFF(run_ts, prev_run_ts, SECOND) > CAST(${INTERVAL_SEC} AS INT64) * 1.5
ORDER BY gap_sec DESC, run_ts DESC
SQL
)

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false --format=csv "$SUMMARY_QUERY" > "$SUMMARY_CSV"
bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false --format=csv "$GAPS_QUERY" > "$GAPS_CSV"

echo "Wrote ${SUMMARY_CSV}"
echo "Wrote ${GAPS_CSV}"
