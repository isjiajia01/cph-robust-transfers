#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <PROJECT_ID> [REGION] [BASE_URL] [CRON_EXPR] [SCHEDULER_REGION]"
  echo "Example: $0 cph-robust-transfers-260302 europe-north1 https://www.rejseplanen.dk/api '*/3 * * * *' europe-west1"
  exit 1
fi

PROJECT_ID="$1"
REGION="${2:-europe-north1}"
BASE_URL="${3:-https://www.rejseplanen.dk/api}"
CRON_EXPR="${4:-*/3 * * * *}"
SCHEDULER_REGION="${5:-$REGION}"
if [[ "$SCHEDULER_REGION" == "europe-north1" ]]; then
  SCHEDULER_REGION="europe-west1"
fi

echo "[1/4] Bootstrap project resources"
bash infra/gcp/bootstrap_project.sh "$PROJECT_ID" "$REGION"

echo "[2/4] Ensure API key in Secret Manager"
bash infra/gcp/setup_secret.sh "$PROJECT_ID"

echo "[3/4] Deploy Cloud Run collector job"
bash infra/gcp/deploy_collector_job.sh "$PROJECT_ID" "$REGION" "$BASE_URL"

echo "[4/4] Create Cloud Scheduler trigger"
bash infra/gcp/create_scheduler.sh "$PROJECT_ID" "$REGION" "$CRON_EXPR" "$SCHEDULER_REGION"

echo "Done."
echo "Smoke test:"
echo "gcloud run jobs execute cph-rt-collector --region \"$REGION\" --project \"$PROJECT_ID\" --wait"
