#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <PROJECT_ID> <REGION>"
  exit 1
fi

PROJECT_ID="$1"
REGION="$2"
RAW_BUCKET="${PROJECT_ID}-cph-rt-raw"
STRUCTURED_BUCKET="${PROJECT_ID}-cph-rt-structured"
AR_REPO="cph-rt"
BQ_DATASET="cph_rt"
RUN_SA="cph-rt-job@${PROJECT_ID}.iam.gserviceaccount.com"
SCHED_SA="cph-rt-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com

if ! gcloud storage buckets describe "gs://${RAW_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${RAW_BUCKET}" --location="$REGION"
fi
if ! gcloud storage buckets describe "gs://${STRUCTURED_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${STRUCTURED_BUCKET}" --location="$REGION"
fi

if ! gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" --repository-format=docker --location="$REGION"
fi

if ! gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create cph-rt-job --display-name="CPH RT Collector Job"
fi
if ! gcloud iam service-accounts describe "$SCHED_SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create cph-rt-scheduler --display-name="CPH RT Scheduler"
fi

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" --role="roles/storage.objectAdmin" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" --role="roles/bigquery.jobUser" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" --role="roles/bigquery.dataViewer" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" --role="roles/bigquery.dataEditor" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" --role="roles/secretmanager.secretAccessor" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" --role="roles/logging.logWriter" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SCHED_SA}" --role="roles/run.invoker" >/dev/null

if ! bq --project_id="$PROJECT_ID" show --dataset "${PROJECT_ID}:${BQ_DATASET}" >/dev/null 2>&1; then
  bq --project_id="$PROJECT_ID" mk --dataset --location="$REGION" "${PROJECT_ID}:${BQ_DATASET}"
fi

echo "PROJECT_ID=$PROJECT_ID"
echo "REGION=$REGION"
echo "RAW_BUCKET=$RAW_BUCKET"
echo "STRUCTURED_BUCKET=$STRUCTURED_BUCKET"
echo "BQ_DATASET=$BQ_DATASET"
echo "RUN_SA=$RUN_SA"
echo "SCHED_SA=$SCHED_SA"
echo "NEXT: create secret REJSEPLANEN_API_KEY if missing"
