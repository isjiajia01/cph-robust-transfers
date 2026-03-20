#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> <STRUCTURED_BUCKET> <START_DATE> [END_DATE] [BQ_LOCATION]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
STRUCTURED_BUCKET="$3"
START_DATE="$4"
END_DATE="${5:-$START_DATE}"
BQ_LOCATION="${6:-europe-north1}"
TMP_DATASET="${DATASET}_backfill_tmp"

next_date() {
  python3 - "$1" <<'PY'
from datetime import date, timedelta
import sys

print((date.fromisoformat(sys.argv[1]) + timedelta(days=1)).isoformat())
PY
}

gcloud config set project "$PROJECT_ID" >/dev/null

if ! bq --project_id="$PROJECT_ID" show --format=none "$PROJECT_ID:$TMP_DATASET" >/dev/null 2>&1; then
  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" mk --dataset "$PROJECT_ID:$TMP_DATASET" >/dev/null
fi

DEPARTURES_SCHEMA="obs_ts_utc:STRING,run_id:STRING,station_gtfs_id:STRING,api_station_id:STRING,line:STRING,mode:STRING,direction:STRING,planned_dep_ts:STRING,realtime_dep_ts:STRING,delay_sec:STRING,journey_ref:STRING"
JOURNEY_SCHEMA="obs_ts_utc:STRING,run_id:STRING,journey_ref:STRING,seq:INTEGER,stop_api_id:STRING,planned_arr_ts:STRING,realtime_arr_ts:STRING,planned_dep_ts:STRING,realtime_dep_ts:STRING,delay_arr_sec:STRING,delay_dep_sec:STRING"
OBS_SCHEMA="run_id:STRING,trigger_id:STRING,scheduled_ts_utc:STRING,job_start_ts_utc:STRING,request_ts:STRING,ingest_ts_utc:STRING,endpoint:STRING,station_batch:STRING,status:INTEGER,latency_ms:INTEGER,records_emitted:INTEGER,collector_version:STRING,sampling_target_version:STRING"
ERROR_SCHEMA="obs_ts_utc:STRING,ingest_ts_utc:STRING,run_id:STRING,trigger_id:STRING,endpoint:STRING,http_code:INTEGER,error_code:STRING,message:STRING,station_id:STRING,journey_ref:STRING,latency_ms:INTEGER,retry_count:INTEGER,request_id:STRING,is_retry_final:BOOLEAN"
RUN_SCHEMA="run_id:STRING,trigger_id:STRING,scheduled_ts_utc:STRING,job_start_ts_utc:STRING,job_end_ts_utc:STRING,duration_sec:INTEGER,schedule_interval_sec:INTEGER,station_count:INTEGER,board_request_count:INTEGER,journey_request_count:INTEGER,success_count:INTEGER,error_count:INTEGER,status_2xx_count:INTEGER,status_4xx_count:INTEGER,status_5xx_count:INTEGER,run_status:STRING,collector_version:STRING,sampling_target_version:STRING"

date_cursor="$START_DATE"
while [[ "$date_cursor" < "$END_DATE" || "$date_cursor" == "$END_DATE" ]]; do
  uri_base="gs://${STRUCTURED_BUCKET}/structured/dt=${date_cursor}/run_id=*"
  if ! gcloud storage ls "${uri_base}/run_metrics.csv" >/dev/null 2>&1; then
    echo "skip dt=${date_cursor}: no structured files found"
    date_cursor="$(next_date "$date_cursor")"
    continue
  fi

  echo "backfill dt=${date_cursor}"

  bq --project_id="$PROJECT_ID" rm -f -t "${TMP_DATASET}.departures_tmp" >/dev/null 2>&1 || true
  bq --project_id="$PROJECT_ID" rm -f -t "${TMP_DATASET}.journey_stops_tmp" >/dev/null 2>&1 || true
  bq --project_id="$PROJECT_ID" rm -f -t "${TMP_DATASET}.observations_tmp" >/dev/null 2>&1 || true
  bq --project_id="$PROJECT_ID" rm -f -t "${TMP_DATASET}.api_errors_tmp" >/dev/null 2>&1 || true
  bq --project_id="$PROJECT_ID" rm -f -t "${TMP_DATASET}.run_metrics_tmp" >/dev/null 2>&1 || true

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" load --replace --source_format=CSV --skip_leading_rows=1 \
    "${TMP_DATASET}.departures_tmp" "${uri_base}/departures.csv" "$DEPARTURES_SCHEMA" >/dev/null

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" load --replace --source_format=CSV --skip_leading_rows=1 \
    "${TMP_DATASET}.journey_stops_tmp" "${uri_base}/journey_stops.csv" "$JOURNEY_SCHEMA" >/dev/null

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" load --replace --source_format=CSV --skip_leading_rows=1 --allow_jagged_rows \
    "${TMP_DATASET}.observations_tmp" "${uri_base}/observations.csv" "$OBS_SCHEMA" >/dev/null

  if gcloud storage ls "${uri_base}/api_errors.csv" >/dev/null 2>&1; then
    bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" load --replace --source_format=CSV --skip_leading_rows=1 --allow_jagged_rows \
      "${TMP_DATASET}.api_errors_tmp" "${uri_base}/api_errors.csv" "$ERROR_SCHEMA" >/dev/null
  else
    bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" mk --table "${TMP_DATASET}.api_errors_tmp" "$ERROR_SCHEMA" >/dev/null
  fi

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" load --replace --source_format=CSV --skip_leading_rows=1 --allow_jagged_rows \
    "${TMP_DATASET}.run_metrics_tmp" "${uri_base}/run_metrics.csv" "$RUN_SCHEMA" >/dev/null

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --nouse_legacy_sql >/dev/null "
MERGE \`${PROJECT_ID}.${DATASET}.run_metrics\` T
USING \`${PROJECT_ID}.${TMP_DATASET}.run_metrics_tmp\` S
ON T.run_id = S.run_id
WHEN NOT MATCHED THEN
  INSERT ROW"

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --nouse_legacy_sql >/dev/null "
MERGE \`${PROJECT_ID}.${DATASET}.observations\` T
USING \`${PROJECT_ID}.${TMP_DATASET}.observations_tmp\` S
ON T.run_id = S.run_id
 AND COALESCE(T.endpoint, '') = COALESCE(S.endpoint, '')
 AND COALESCE(T.station_batch, '') = COALESCE(S.station_batch, '')
 AND COALESCE(T.request_ts, '') = COALESCE(S.request_ts, '')
WHEN NOT MATCHED THEN
  INSERT ROW"

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --nouse_legacy_sql >/dev/null "
MERGE \`${PROJECT_ID}.${DATASET}.departures\` T
USING \`${PROJECT_ID}.${TMP_DATASET}.departures_tmp\` S
ON T.run_id = S.run_id
 AND COALESCE(T.api_station_id, '') = COALESCE(S.api_station_id, '')
 AND COALESCE(T.journey_ref, '') = COALESCE(S.journey_ref, '')
 AND COALESCE(T.planned_dep_ts, '') = COALESCE(S.planned_dep_ts, '')
WHEN NOT MATCHED THEN
  INSERT ROW"

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --nouse_legacy_sql >/dev/null "
MERGE \`${PROJECT_ID}.${DATASET}.journey_stops\` T
USING \`${PROJECT_ID}.${TMP_DATASET}.journey_stops_tmp\` S
ON T.run_id = S.run_id
 AND COALESCE(T.journey_ref, '') = COALESCE(S.journey_ref, '')
 AND COALESCE(T.stop_api_id, '') = COALESCE(S.stop_api_id, '')
 AND COALESCE(T.seq, -1) = COALESCE(S.seq, -1)
 AND COALESCE(T.planned_arr_ts, '') = COALESCE(S.planned_arr_ts, '')
 AND COALESCE(T.planned_dep_ts, '') = COALESCE(S.planned_dep_ts, '')
WHEN NOT MATCHED THEN
  INSERT ROW"

  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --nouse_legacy_sql >/dev/null "
MERGE \`${PROJECT_ID}.${DATASET}.api_errors\` T
USING \`${PROJECT_ID}.${TMP_DATASET}.api_errors_tmp\` S
ON COALESCE(T.request_id, '') = COALESCE(S.request_id, '')
 AND COALESCE(T.run_id, '') = COALESCE(S.run_id, '')
WHEN NOT MATCHED THEN
  INSERT ROW"

  date_cursor="$(next_date "$date_cursor")"
done

echo "backfill complete ${START_DATE}..${END_DATE}"
