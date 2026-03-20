#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> [STRUCTURED_BUCKET] [BQ_LOCATION] [INTERVAL_SEC]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
STRUCTURED_BUCKET="${3:-${PROJECT_ID}-cph-rt-structured}"
BQ_LOCATION="${4:-europe-north1}"
INTERVAL_SEC="${5:-180}"

TODAY_UTC="$(date -u +%F)"
YESTERDAY_UTC="$(date -u -v-1d +%F 2>/dev/null || date -u -d 'yesterday' +%F)"

mkdir -p data/analysis

echo "[1/5] Load structured dt=${YESTERDAY_UTC}"
bash infra/bigquery/load_structured.sh "$PROJECT_ID" "$DATASET" "$STRUCTURED_BUCKET" "$YESTERDAY_UTC" || true

echo "[2/5] Load structured dt=${TODAY_UTC}"
bash infra/bigquery/load_structured.sh "$PROJECT_ID" "$DATASET" "$STRUCTURED_BUCKET" "$TODAY_UTC"

echo "[3/6] Create Copenhagen time-feature views"
bash infra/bigquery/create_cph_time_features.sh "$PROJECT_ID" "$DATASET" "$BQ_LOCATION"

echo "[4/6] Export quantiles"
bash infra/bigquery/run_delay_quantiles.sh "$PROJECT_ID" "$DATASET" "data/analysis/delay_quantiles_bq.csv" "$BQ_LOCATION"

echo "[5/6] 24h sampling integrity check"
bash infra/bigquery/check_sampling_integrity_24h.sh "$PROJECT_ID" "$DATASET" "$INTERVAL_SEC" "data/analysis" "$BQ_LOCATION"

echo "[6/6] Update docs/week3_summary.md"
python3 -m src.realtime.update_week3_summary \
  --project-id "$PROJECT_ID" \
  --dataset "$DATASET" \
  --quantiles "data/analysis/delay_quantiles_bq.csv" \
  --integrity "data/analysis/sampling_integrity_24h.csv" \
  --gaps "data/analysis/sampling_gaps_24h.csv" \
  --out "docs/week3_summary.md"

echo "Done."
