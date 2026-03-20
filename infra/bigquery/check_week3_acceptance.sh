#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> [BQ_LOCATION] [MIN_COVERAGE] [MAX_CRITICAL_GAPS] [MAX_429_RATIO]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
BQ_LOCATION="${3:-europe-north1}"
MIN_COVERAGE="${4:-0.90}"
MAX_CRITICAL_GAPS="${5:-0}"
MAX_429_RATIO="${6:-0.05}"

query="$(cat <<SQL
SELECT generated_at_utc, coverage_ratio, critical_gap_count, error_429_ratio, max_gap_sec
FROM \`${PROJECT_ID}.${DATASET}.daily_summary\`
ORDER BY generated_at_utc DESC
LIMIT 1
SQL
)"

row="$(bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --nouse_legacy_sql --format=csv "$query" | tail -n 1)"
if [[ -z "$row" ]]; then
  echo "status=FAIL reason=no_daily_summary_rows"
  exit 2
fi

IFS=',' read -r generated_at coverage critical gaps max_gap <<< "$row"
coverage="${coverage:-0}"
gaps="${gaps:-999999}"
critical="${critical:-0}"
max_gap="${max_gap:-0}"

status="PASS"
reason="ok"

python3 - <<'PY' "$coverage" "$critical" "$gaps" "$MIN_COVERAGE" "$MAX_CRITICAL_GAPS" "$MAX_429_RATIO" >/tmp/week3_acceptance_eval.txt
import sys
cov=float(sys.argv[1] or 0)
critical=int(float(sys.argv[2] or 0))
ratio=float(sys.argv[3] or 0)
min_cov=float(sys.argv[4])
max_critical=int(float(sys.argv[5]))
max_ratio=float(sys.argv[6])
ok=(cov>=min_cov and critical<=max_critical and ratio<=max_ratio)
reasons=[]
if cov<min_cov:
    reasons.append(f"coverage<{min_cov}")
if critical>max_critical:
    reasons.append(f"critical_gap_count>{max_critical}")
if ratio>max_ratio:
    reasons.append(f"error_429_ratio>{max_ratio}")
print("PASS" if ok else "FAIL")
print("ok" if ok else ";".join(reasons))
PY

status="$(sed -n '1p' /tmp/week3_acceptance_eval.txt)"
reason="$(sed -n '2p' /tmp/week3_acceptance_eval.txt)"

echo "generated_at_utc=$generated_at"
echo "coverage_ratio=$coverage"
echo "critical_gap_count=$critical"
echo "error_429_ratio=$gaps"
echo "max_gap_sec=$max_gap"
echo "status=$status"
echo "reason=$reason"

if [[ "$status" != "PASS" ]]; then
  exit 3
fi
