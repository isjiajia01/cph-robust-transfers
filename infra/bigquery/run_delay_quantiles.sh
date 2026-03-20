#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> <OUTPUT_CSV_PATH> [BQ_LOCATION]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
OUTPUT_CSV="$3"
BQ_LOCATION="${4:-europe-north1}"
TABLE_REF="\`${PROJECT_ID}.${DATASET}.departures\`"

mkdir -p "$(dirname "$OUTPUT_CSV")"

QUERY=$(cat <<SQL
WITH cleaned AS (
  SELECT
    line,
    SAFE.TIMESTAMP(realtime_dep_ts) AS realtime_ts,
    SAFE.TIMESTAMP(planned_dep_ts) AS planned_ts
  FROM ${TABLE_REF}
)
SELECT
  line,
  APPROX_QUANTILES(TIMESTAMP_DIFF(realtime_ts, planned_ts, SECOND), 100)[OFFSET(50)] AS p50_delay_sec,
  APPROX_QUANTILES(TIMESTAMP_DIFF(realtime_ts, planned_ts, SECOND), 100)[OFFSET(90)] AS p90_delay_sec,
  APPROX_QUANTILES(TIMESTAMP_DIFF(realtime_ts, planned_ts, SECOND), 100)[OFFSET(95)] AS p95_delay_sec,
  COUNT(*) AS n
FROM cleaned
WHERE realtime_ts IS NOT NULL AND planned_ts IS NOT NULL
GROUP BY line
ORDER BY p95_delay_sec DESC
SQL
)

bq --project_id="$PROJECT_ID" query --location="$BQ_LOCATION" --use_legacy_sql=false --format=csv "$QUERY" > "$OUTPUT_CSV"
echo "Wrote ${OUTPUT_CSV}"
