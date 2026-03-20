#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <PROJECT_ID> [NOTIFICATION_CHANNEL]"
  echo "Example: $0 cph-robust-transfers-260302 projects/<p>/notificationChannels/<id>"
  exit 1
fi

PROJECT_ID="$1"
NOTIFICATION_CHANNEL="${2:-}"
METRIC_NAME="cph_rt_alert_drill_count"
POLICY_NAME="CPH RT Alert Drill"
LOG_NAME="cph-alert-drill"
DRILL_TOKEN="CPH_ALERT_DRILL_TOKEN_$(date -u +%Y%m%dT%H%M%SZ)"

FILTER="resource.type=\"global\" AND logName=\"projects/${PROJECT_ID}/logs/${LOG_NAME}\" AND textPayload:\"CPH_ALERT_DRILL_TOKEN\""

gcloud config set project "$PROJECT_ID" >/dev/null

if gcloud logging metrics describe "$METRIC_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud logging metrics update "$METRIC_NAME" \
    --project "$PROJECT_ID" \
    --description "Alert drill counter for week3 notification path" \
    --log-filter "$FILTER" >/dev/null
  echo "updated_metric=$METRIC_NAME"
else
  gcloud logging metrics create "$METRIC_NAME" \
    --project "$PROJECT_ID" \
    --description "Alert drill counter for week3 notification path" \
    --log-filter "$FILTER" >/dev/null
  echo "created_metric=$METRIC_NAME"
fi

policy_id="$(gcloud monitoring policies list --project "$PROJECT_ID" --format='value(name)' --filter="displayName=\"${POLICY_NAME}\"" | head -n1)"

channels_json='[]'
if [[ -n "$NOTIFICATION_CHANNEL" ]]; then
  channels_json="$(python3 - <<'PY' "$NOTIFICATION_CHANNEL"
import json, sys
print(json.dumps([sys.argv[1]]))
PY
)"
fi

policy_file="$(mktemp /tmp/cph-alert-drill-policy.XXXXXX.json)"
cat > "$policy_file" <<JSON
{
  "displayName": "${POLICY_NAME}",
  "combiner": "OR",
  "enabled": true,
  "conditions": [
    {
      "displayName": "Drill metric > 0",
      "conditionThreshold": {
        "filter": "metric.type=\"logging.googleapis.com/user/${METRIC_NAME}\" AND resource.type=\"global\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0,
        "duration": "0s",
        "aggregations": [{"alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_SUM"}],
        "trigger": {"count": 1}
      }
    }
  ],
  "documentation": {
    "content": "Week3 alert drill policy. Triggered by writing a log with token CPH_ALERT_DRILL_TOKEN.",
    "mimeType": "text/markdown"
  },
  "notificationChannels": ${channels_json},
  "alertStrategy": {"autoClose": "1800s"}
}
JSON

if [[ -n "$policy_id" ]]; then
  gcloud monitoring policies update "$policy_id" --project "$PROJECT_ID" --policy-from-file "$policy_file" >/dev/null
  echo "updated_policy=$POLICY_NAME"
else
  gcloud monitoring policies create --project "$PROJECT_ID" --policy-from-file "$policy_file" >/dev/null
  echo "created_policy=$POLICY_NAME"
fi
rm -f "$policy_file"

gcloud logging write "$LOG_NAME" "$DRILL_TOKEN" --project "$PROJECT_ID" --payload-type=text >/dev/null

echo "drill_log_token=$DRILL_TOKEN"
echo "log_written=projects/${PROJECT_ID}/logs/${LOG_NAME}"
echo "next=check email channel for policy '${POLICY_NAME}' incident notification in 1-5 minutes"
