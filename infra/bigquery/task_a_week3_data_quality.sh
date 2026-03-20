#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> <REPORT_BUCKET> [BQ_LOCATION] [INTERVAL_SEC]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
REPORT_BUCKET="$3"
BQ_LOCATION="${4:-europe-north1}"
INTERVAL_SEC="${5:-180}"
DATE_UTC="$(date -u +%F)"
REPORT_DIR="data/analysis/reports/week3/dt=${DATE_UTC}"

mkdir -p "$REPORT_DIR"

echo "[1/4] Export quantiles and sampling integrity"
bash infra/bigquery/run_delay_quantiles.sh "$PROJECT_ID" "$DATASET" "${REPORT_DIR}/delay_quantiles_bq.csv" "$BQ_LOCATION"
bash infra/bigquery/check_sampling_integrity_24h.sh "$PROJECT_ID" "$DATASET" "$INTERVAL_SEC" "$REPORT_DIR" "$BQ_LOCATION"

echo "[2/4] Build summary.json and summary.md"
python3 -m src.realtime.update_week3_summary \
  --project-id "$PROJECT_ID" \
  --dataset "$DATASET" \
  --quantiles "${REPORT_DIR}/delay_quantiles_bq.csv" \
  --integrity "${REPORT_DIR}/sampling_integrity_24h.csv" \
  --gaps "${REPORT_DIR}/sampling_gaps_24h.csv" \
  --json-out "${REPORT_DIR}/summary.json" \
  --out "${REPORT_DIR}/summary.md"

echo "[3/4] Upload dt partition report files"
gcloud storage cp "${REPORT_DIR}/summary.json" "gs://${REPORT_BUCKET}/reports/week3/dt=${DATE_UTC}/summary.json"
gcloud storage cp "${REPORT_DIR}/summary.md" "gs://${REPORT_BUCKET}/reports/week3/dt=${DATE_UTC}/summary.md"
gcloud storage cp "${REPORT_DIR}/delay_quantiles_bq.csv" "gs://${REPORT_BUCKET}/reports/week3/dt=${DATE_UTC}/delay_quantiles_bq.csv"
gcloud storage cp "${REPORT_DIR}/sampling_integrity_24h.csv" "gs://${REPORT_BUCKET}/reports/week3/dt=${DATE_UTC}/sampling_integrity_24h.csv"
gcloud storage cp "${REPORT_DIR}/sampling_gaps_24h.csv" "gs://${REPORT_BUCKET}/reports/week3/dt=${DATE_UTC}/sampling_gaps_24h.csv"

echo "[4/4] Update latest pointers"
gcloud storage cp "${REPORT_DIR}/summary.json" "gs://${REPORT_BUCKET}/reports/week3/latest/summary.json"
gcloud storage cp "${REPORT_DIR}/summary.md" "gs://${REPORT_BUCKET}/reports/week3/latest/summary.md"
gcloud storage cp "${REPORT_DIR}/delay_quantiles_bq.csv" "gs://${REPORT_BUCKET}/reports/week3/latest/delay_quantiles_bq.csv"
gcloud storage cp "${REPORT_DIR}/sampling_integrity_24h.csv" "gs://${REPORT_BUCKET}/reports/week3/latest/sampling_integrity_24h.csv"
gcloud storage cp "${REPORT_DIR}/sampling_gaps_24h.csv" "gs://${REPORT_BUCKET}/reports/week3/latest/sampling_gaps_24h.csv"

echo "Done."
echo "dt report: gs://${REPORT_BUCKET}/reports/week3/dt=${DATE_UTC}/summary.json"
echo "latest:    gs://${REPORT_BUCKET}/reports/week3/latest/summary.json"
