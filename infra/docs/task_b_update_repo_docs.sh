#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <REPORT_BUCKET>"
  exit 1
fi

REPORT_BUCKET="$1"
TMP_DIR="data/analysis/reports/week3/latest"

mkdir -p "$TMP_DIR"

echo "[1/2] Download latest report artifacts from GCS"
gcloud storage cp "gs://${REPORT_BUCKET}/reports/week3/latest/summary.json" "${TMP_DIR}/summary.json"

echo "[2/2] Render docs/week3_summary.md from summary.json"
python3 -m src.realtime.render_week3_md_from_json \
  --input-json "${TMP_DIR}/summary.json" \
  --out "docs/week3_summary.md"

echo "Updated docs/week3_summary.md"
