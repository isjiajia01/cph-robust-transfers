#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <PROJECT_ID> <REGION> <REJSEPLANEN_BASE_URL>"
  exit 1
fi

PROJECT_ID="$1"
REGION="$2"
BASE_URL="$3"
JOB_NAME="cph-rt-collector"
AR_REPO="cph-rt"
RAW_BUCKET="${PROJECT_ID}-cph-rt-raw"
STRUCTURED_BUCKET="${PROJECT_ID}-cph-rt-structured"
RUN_SA="cph-rt-job@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/realtime-collector:$(date +%Y%m%d-%H%M%S)"
COLLECTOR_VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
BQ_DATASET="cph_rt"

gcloud config set project "$PROJECT_ID"
gcloud builds submit --tag "$IMAGE_URI"

gcloud run jobs deploy "$JOB_NAME" \
  --region "$REGION" \
  --image "$IMAGE_URI" \
  --service-account "$RUN_SA" \
  --set-secrets "REJSEPLANEN_API_KEY=REJSEPLANEN_API_KEY:latest" \
  --set-env-vars "PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DATASET},REJSEPLANEN_BASE_URL=${BASE_URL},GCS_BUCKET_RAW=${RAW_BUCKET},GCS_BUCKET_STRUCTURED=${STRUCTURED_BUCKET},COLLECTOR_VERSION=${COLLECTOR_VERSION}" \
  --task-timeout 1800s \
  --max-retries 1 \
  --command /bin/sh \
  --args -lc,"python -m src.realtime.collector --config configs/pipeline.defaults.toml --stations configs/stations_seed.csv --base-url ${BASE_URL} --once"

echo "JOB_NAME=$JOB_NAME"
echo "IMAGE_URI=$IMAGE_URI"
