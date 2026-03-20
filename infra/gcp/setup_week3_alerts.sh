#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <PROJECT_ID> [NOTIFICATION_CHANNELS_CSV]"
  echo "Example: $0 cph-robust-transfers-260302 projects/xxx/notificationChannels/123"
  exit 1
fi

PROJECT_ID="$1"
NOTIFICATION_CHANNELS_CSV="${2:-}"
COLLECTOR_JOB="cph-rt-collector"

METRIC_429="cph_rt_api_too_many_requests_count"
METRIC_QUOTA="cph_rt_api_quota_count"

FILTER_BASE="resource.labels.job_name=\"${COLLECTOR_JOB}\" AND (logName=\"projects/${PROJECT_ID}/logs/run.googleapis.com%2Fstdout\" OR logName=\"projects/${PROJECT_ID}/logs/run.googleapis.com%2Fstderr\")"
FILTER_429="${FILTER_BASE} AND (textPayload:\"API_TOO_MANY_REQUESTS\" OR textPayload:\"\\\"http_code\\\": 429\")"
FILTER_QUOTA="${FILTER_BASE} AND textPayload:\"API_QUOTA\""

gcloud config set project "$PROJECT_ID" >/dev/null

upsert_metric() {
  local name="$1"
  local description="$2"
  local filter="$3"
  if gcloud logging metrics describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud logging metrics update "$name" \
      --project "$PROJECT_ID" \
      --description "$description" \
      --log-filter "$filter" >/dev/null
    echo "updated_metric=$name"
  else
    gcloud logging metrics create "$name" \
      --project "$PROJECT_ID" \
      --description "$description" \
      --log-filter "$filter" >/dev/null
    echo "created_metric=$name"
  fi
}

upsert_policy() {
  local display_name="$1"
  local metric_name="$2"
  local documentation="$3"

  local policy_id
  policy_id="$(gcloud monitoring policies list --project "$PROJECT_ID" --format='value(name)' --filter="displayName=\"${display_name}\"" | head -n1)"

  local channels_json="[]"
  if [[ -n "$NOTIFICATION_CHANNELS_CSV" ]]; then
    channels_json="$(python3 - <<'PY' "$NOTIFICATION_CHANNELS_CSV"
import json, sys
vals=[x.strip() for x in sys.argv[1].split(',') if x.strip()]
print(json.dumps(vals))
PY
)"
  fi

  local policy_file
  policy_file="$(mktemp /tmp/cph-alert-policy.XXXXXX.json)"

  cat > "$policy_file" <<JSON
{
  "displayName": "${display_name}",
  "combiner": "OR",
  "enabled": true,
  "conditions": [
    {
      "displayName": "${display_name} condition",
      "conditionThreshold": {
        "filter": "metric.type=\"logging.googleapis.com/user/${metric_name}\" AND resource.type=\"global\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0,
        "duration": "0s",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_SUM"
          }
        ],
        "trigger": {
          "count": 1
        }
      }
    }
  ],
  "documentation": {
    "content": "${documentation}",
    "mimeType": "text/markdown"
  },
  "notificationChannels": ${channels_json},
  "alertStrategy": {
    "autoClose": "1800s"
  }
}
JSON

  if [[ -n "$policy_id" ]]; then
    gcloud monitoring policies update "$policy_id" \
      --project "$PROJECT_ID" \
      --policy-from-file "$policy_file" >/dev/null
    echo "updated_policy=${display_name}"
  else
    gcloud monitoring policies create \
      --project "$PROJECT_ID" \
      --policy-from-file "$policy_file" >/dev/null
    echo "created_policy=${display_name}"
  fi

  rm -f "$policy_file"
}

upsert_metric "$METRIC_429" "Count of collector logs containing API_TOO_MANY_REQUESTS / HTTP 429" "$FILTER_429"
upsert_metric "$METRIC_QUOTA" "Count of collector logs containing API_QUOTA" "$FILTER_QUOTA"

upsert_policy \
  "CPH RT API_TOO_MANY_REQUESTS detected" \
  "$METRIC_429" \
  "Collector reported API_TOO_MANY_REQUESTS / HTTP 429. Check run_gap_diagnostics and api_errors for throttling root cause."

upsert_policy \
  "CPH RT API_QUOTA detected" \
  "$METRIC_QUOTA" \
  "Collector reported API_QUOTA. Reduce sampling pressure or increase quota before reliability degrades."

echo "project_id=$PROJECT_ID"
echo "collector_job=$COLLECTOR_JOB"
if [[ -z "$NOTIFICATION_CHANNELS_CSV" ]]; then
  echo "notification_channels=none (set second arg to attach channels)"
else
  echo "notification_channels=$NOTIFICATION_CHANNELS_CSV"
fi
