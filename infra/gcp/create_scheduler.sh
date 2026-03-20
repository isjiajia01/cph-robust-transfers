#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <PROJECT_ID> <RUN_REGION> <CRON_EXPR> [SCHEDULER_REGION]"
  exit 1
fi

PROJECT_ID="$1"
RUN_REGION="$2"
CRON_EXPR="$3"
SCHEDULER_REGION="${4:-$RUN_REGION}"
JOB_NAME="cph-rt-collector"
SCHEDULER_NAME="cph-rt-collector-every-3min"
SCHED_SA="cph-rt-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
TARGET_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${RUN_REGION}/jobs/${JOB_NAME}:run"

gcloud config set project "$PROJECT_ID"

gcloud scheduler jobs delete "$SCHEDULER_NAME" --location="$SCHEDULER_REGION" --quiet >/dev/null 2>&1 || true
gcloud scheduler jobs create http "$SCHEDULER_NAME" \
  --location "$SCHEDULER_REGION" \
  --schedule "$CRON_EXPR" \
  --uri "$TARGET_URI" \
  --http-method POST \
  --oauth-service-account-email "$SCHED_SA"

echo "SCHEDULER_NAME=$SCHEDULER_NAME"
echo "RUN_REGION=$RUN_REGION"
echo "SCHEDULER_REGION=$SCHEDULER_REGION"
echo "CRON=$CRON_EXPR"
