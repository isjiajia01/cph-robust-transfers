#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <PROJECT_ID> <DATASET> [BQ_LOCATION] [OUT_MD]"
  exit 1
fi

PROJECT_ID="$1"
DATASET="$2"
BQ_LOCATION="${3:-europe-north1}"
OUT_MD="${4:-docs/week3_ops_status.md}"

query="$(cat <<SQL
SELECT dt_local, generated_at_utc, coverage_ratio, critical_gap_count, max_gap_sec, error_429_ratio, duplicate_ratio, sample_size_total
FROM \`${PROJECT_ID}.${DATASET}.daily_summary\`
ORDER BY generated_at_utc DESC
LIMIT 1
SQL
)"

csv="$(bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --nouse_legacy_sql --format=csv "$query")"
row="$(printf '%s\n' "$csv" | tail -n 1)"
if [[ -z "$row" ]]; then
  echo "No rows in ${PROJECT_ID}.${DATASET}.daily_summary"
  exit 2
fi

IFS=',' read -r dt_local generated_at cov critical max_gap err429 dup_ratio sample_size <<< "$row"

status="PASS"
reason="ok"
python3 - <<'PY' "$cov" "$critical" "$err429" > /tmp/week3_status_eval.txt
import sys
cov=float(sys.argv[1] or 0)
critical=int(float(sys.argv[2] or 0))
err=float(sys.argv[3] or 0)
ok=(cov>=0.90 and critical<=0 and err<=0.05)
reasons=[]
if cov<0.90:
    reasons.append("coverage<0.90")
if critical>0:
    reasons.append("critical_gap_count>0")
if err>0.05:
    reasons.append("error_429_ratio>0.05")
print("PASS" if ok else "FAIL")
print("ok" if ok else ";".join(reasons))
PY
status="$(sed -n '1p' /tmp/week3_status_eval.txt)"
reason="$(sed -n '2p' /tmp/week3_status_eval.txt)"

mkdir -p "$(dirname "$OUT_MD")"
cat > "$OUT_MD" <<MD
# Week3 Ops Status

- Snapshot generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- Source project: \`${PROJECT_ID}\`
- Source dataset: \`${DATASET}\`

## Latest daily_summary row
- dt_local: \`${dt_local}\`
- generated_at_utc: \`${generated_at}\`
- coverage_ratio: \`${cov}\`
- critical_gap_count: \`${critical}\`
- max_gap_sec: \`${max_gap}\`
- error_429_ratio: \`${err429}\`
- duplicate_ratio: \`${dup_ratio}\`
- sample_size_total: \`${sample_size}\`

## Acceptance Gate (target: coverage>=0.90, critical_gap_count=0, error_429_ratio<=0.05)
- status: \`${status}\`
- reason: \`${reason}\`
MD

echo "$OUT_MD"
