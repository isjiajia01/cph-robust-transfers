#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <PROJECT_ID> <REGION> [BQ_DATASET] [REPORT_BUCKET] [BQ_LOCATION] [INTERVAL_SEC] [REPORT_TIMEZONE]"
  exit 1
fi

PROJECT_ID="$1"
REGION="$2"
BQ_DATASET="${3:-cph_rt}"
REPORT_BUCKET="${4:-${PROJECT_ID}-cph-rt-raw}"
BQ_LOCATION="${5:-$REGION}"
INTERVAL_SEC="${6:-180}"
REPORT_TIMEZONE="${7:-Europe/Copenhagen}"
JOB_NAME="cph-week3-data-quality"
AR_REPO="cph-rt"
RUN_SA="cph-rt-job@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/week3-reports:$(date +%Y%m%d-%H%M%S)"

gcloud config set project "$PROJECT_ID"
gcloud builds submit --tag "$IMAGE_URI"

gcloud run jobs deploy "$JOB_NAME" \
  --region "$REGION" \
  --image "$IMAGE_URI" \
  --service-account "$RUN_SA" \
  --set-env-vars "PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DATASET},REPORT_BUCKET=${REPORT_BUCKET},BQ_LOCATION=${BQ_LOCATION},INTERVAL_SEC=${INTERVAL_SEC},REPORT_TIMEZONE=${REPORT_TIMEZONE}" \
  --task-timeout 1800s \
  --max-retries 1 \
  --command /bin/sh \
  --args -lc,"python -m src.realtime.task_a_daily_job"

echo "JOB_NAME=$JOB_NAME"
echo "IMAGE_URI=$IMAGE_URI"
echo "REPORT_BUCKET=$REPORT_BUCKET"
