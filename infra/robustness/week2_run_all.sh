#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <EDGES_CSV> <NODES_CSV> [OUT_DIR]"
  echo "Example: $0 data/graph/20260302/edges.csv data/graph/20260302/nodes.csv data/robustness/20260302_high"
  exit 1
fi

EDGES_CSV="$1"
NODES_CSV="$2"
OUT_DIR="${3:-data/robustness/latest}"

K_MAX="${K_MAX:-30}"
STEP="${STEP:-3}"
REPEATS="${REPEATS:-10}"
SEED="${SEED:-42}"
TARGETING="${TARGETING:-betweenness}"
OD_PAIRS="${OD_PAIRS:-500}"
AVGSP_SOURCES="${AVGSP_SOURCES:-96}"
BETWEENNESS_SOURCES="${BETWEENNESS_SOURCES:-96}"
RESULTS_DIR="${RESULTS_DIR:-results/robustness}"
RESULTS_SUMMARY_MD="${RESULTS_SUMMARY_MD:-${RESULTS_DIR}/summary.md}"
NOTEBOOK_OUT="${NOTEBOOK_OUT:-notebooks/02_robustness_experiments.ipynb}"

SUMMARY_CSV="${OUT_DIR}/robustness_summary.csv"
RUNS_CSV="${OUT_DIR}/robustness_runs.csv"
CRITICAL_CSV="${OUT_DIR}/critical_nodes_top10.csv"
CURVE_PNG="docs/figures/week2_random_vs_targeted.png"
EXTRA_PNG="docs/figures/week2_extra_metrics.png"

if [[ "$OUT_DIR" == data/* ]]; then
  NOTEBOOK_BASE="../${OUT_DIR}"
else
  NOTEBOOK_BASE="$OUT_DIR"
fi

mkdir -p "$OUT_DIR"

python3 -m src.robustness.simulate_failures \
  --edges "$EDGES_CSV" \
  --out "$OUT_DIR" \
  --k-max "$K_MAX" \
  --step "$STEP" \
  --repeats "$REPEATS" \
  --seed "$SEED" \
  --targeting "$TARGETING" \
  --od-pairs "$OD_PAIRS" \
  --avgsp-sources "$AVGSP_SOURCES" \
  --betweenness-sources "$BETWEENNESS_SOURCES"

python3 -m src.robustness.report \
  --input "$RUNS_CSV" \
  --out "$SUMMARY_CSV"

python3 -m src.robustness.week2_report \
  --runs "$RUNS_CSV" \
  --edges "$EDGES_CSV" \
  --nodes "$NODES_CSV" \
  --summary "$SUMMARY_CSV" \
  --curve-png "$CURVE_PNG" \
  --extra-png "$EXTRA_PNG" \
  --critical-out "$CRITICAL_CSV" \
  --results-dir "$RESULTS_DIR" \
  --results-summary-md "$RESULTS_SUMMARY_MD" \
  --betweenness-sources "$BETWEENNESS_SOURCES" \
  --seed "$SEED"

python3 -m src.robustness.update_week2_notebook \
  --base-dir "$NOTEBOOK_BASE" \
  --out "$NOTEBOOK_OUT"

echo "week2_out_dir=$OUT_DIR"
echo "summary_csv=$SUMMARY_CSV"
echo "critical_csv=$CRITICAL_CSV"
echo "results_summary_md=$RESULTS_SUMMARY_MD"
echo "notebook=$NOTEBOOK_OUT"
