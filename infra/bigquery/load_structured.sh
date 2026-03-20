#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> <STRUCTURED_BUCKET> <DATE_YYYY-MM-DD>"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
STRUCTURED_BUCKET="$3"
DATE_PART="$4"

URI_BASE="gs://${STRUCTURED_BUCKET}/structured/dt=${DATE_PART}/run_id=*"

gcloud config set project "$PROJECT_ID" >/dev/null

if ! bq --project_id="$PROJECT_ID" show --format=none "$PROJECT_ID:$DATASET" >/dev/null 2>&1; then
  bq --project_id="$PROJECT_ID" mk --dataset "$PROJECT_ID:$DATASET" >/dev/null
fi

# Recreate tables to enforce stable schema names.
bq --project_id="$PROJECT_ID" rm -f -t "${DATASET}.departures" >/dev/null 2>&1 || true
bq --project_id="$PROJECT_ID" rm -f -t "${DATASET}.journey_stops" >/dev/null 2>&1 || true
bq --project_id="$PROJECT_ID" rm -f -t "${DATASET}.observations" >/dev/null 2>&1 || true
bq --project_id="$PROJECT_ID" rm -f -t "${DATASET}.api_errors" >/dev/null 2>&1 || true
bq --project_id="$PROJECT_ID" rm -f -t "${DATASET}.run_metrics" >/dev/null 2>&1 || true

DEPARTURES_SCHEMA="obs_ts_utc:STRING,run_id:STRING,station_gtfs_id:STRING,api_station_id:STRING,line:STRING,mode:STRING,direction:STRING,planned_dep_ts:STRING,realtime_dep_ts:STRING,delay_sec:STRING,journey_ref:STRING"
JOURNEY_SCHEMA="obs_ts_utc:STRING,run_id:STRING,journey_ref:STRING,seq:INTEGER,stop_api_id:STRING,planned_arr_ts:STRING,realtime_arr_ts:STRING,planned_dep_ts:STRING,realtime_dep_ts:STRING,delay_arr_sec:STRING,delay_dep_sec:STRING"
OBS_SCHEMA="run_id:STRING,trigger_id:STRING,scheduled_ts_utc:STRING,job_start_ts_utc:STRING,request_ts:STRING,ingest_ts_utc:STRING,endpoint:STRING,station_batch:STRING,status:INTEGER,latency_ms:INTEGER,records_emitted:INTEGER,collector_version:STRING,sampling_target_version:STRING"
ERROR_SCHEMA="obs_ts_utc:STRING,ingest_ts_utc:STRING,run_id:STRING,trigger_id:STRING,endpoint:STRING,http_code:INTEGER,error_code:STRING,message:STRING,station_id:STRING,journey_ref:STRING,latency_ms:INTEGER,retry_count:INTEGER,request_id:STRING,is_retry_final:BOOLEAN"
RUN_SCHEMA="run_id:STRING,trigger_id:STRING,scheduled_ts_utc:STRING,job_start_ts_utc:STRING,job_end_ts_utc:STRING,duration_sec:INTEGER,schedule_interval_sec:INTEGER,station_count:INTEGER,board_request_count:INTEGER,journey_request_count:INTEGER,success_count:INTEGER,error_count:INTEGER,status_2xx_count:INTEGER,status_4xx_count:INTEGER,status_5xx_count:INTEGER,run_status:STRING,collector_version:STRING,sampling_target_version:STRING"

bq --project_id="$PROJECT_ID" load --source_format=CSV --skip_leading_rows=1 \
  "${DATASET}.departures" "${URI_BASE}/departures.csv" "$DEPARTURES_SCHEMA"

bq --project_id="$PROJECT_ID" load --source_format=CSV --skip_leading_rows=1 \
  "${DATASET}.journey_stops" "${URI_BASE}/journey_stops.csv" "$JOURNEY_SCHEMA"

bq --project_id="$PROJECT_ID" load --source_format=CSV --skip_leading_rows=1 --allow_jagged_rows \
  "${DATASET}.observations" "${URI_BASE}/observations.csv" "$OBS_SCHEMA"

if gcloud storage ls "${URI_BASE}/api_errors.csv" >/dev/null 2>&1; then
  bq --project_id="$PROJECT_ID" load --source_format=CSV --skip_leading_rows=1 --allow_jagged_rows \
    "${DATASET}.api_errors" "${URI_BASE}/api_errors.csv" "$ERROR_SCHEMA"
else
  bq --project_id="$PROJECT_ID" mk --table "${DATASET}.api_errors" "$ERROR_SCHEMA" >/dev/null
fi

if gcloud storage ls "${URI_BASE}/run_metrics.csv" >/dev/null 2>&1; then
  bq --project_id="$PROJECT_ID" load --source_format=CSV --skip_leading_rows=1 --allow_jagged_rows \
    "${DATASET}.run_metrics" "${URI_BASE}/run_metrics.csv" "$RUN_SCHEMA"
else
  bq --project_id="$PROJECT_ID" mk --table "${DATASET}.run_metrics" "$RUN_SCHEMA" >/dev/null
fi

echo "Loaded date partition dt=${DATE_PART} from ${URI_BASE}"
