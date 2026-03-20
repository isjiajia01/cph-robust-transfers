from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render docs/week3_summary.md from summary.json")
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--out", default="docs/week3_summary.md")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    input_path = Path(args.input_json)
    with input_path.open("r", encoding="utf-8") as f:
        summary = json.load(f)

    sampling = summary.get("sampling_24h", {})
    top_lines = (summary.get("top_lines_by_p95") or [])[: args.top_k]
    gaps = (sampling.get("largest_gaps") or [])[:5]
    uncertainty = summary.get("uncertainty", {})
    risk_quantiles = (uncertainty.get("risk_model_quantiles") or [])[:5]
    delay_bands = (uncertainty.get("top_lines_by_p95_band") or [])[:5]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# Week3 Summary\n\n")
        f.write(f"- Generated (UTC): `{summary.get('generated_at_utc', '')}`\n")
        source = summary.get("source", {})
        f.write(f"- Source: BigQuery `{source.get('project_id', '')}.{source.get('dataset', '')}`\n")
        f.write("\n## 24h Sampling Integrity\n")
        f.write(
            f"- Runs observed: `{sampling.get('run_count_24h', 0)}` / expected "
            f"`{sampling.get('expected_runs_24h', 0)}` (coverage `{float(sampling.get('coverage_ratio', 0.0)):.2%}`)\n"
        )
        f.write(f"- Gap warnings (>1.5x interval): `{sampling.get('warning_gap_count', 0)}`\n")
        f.write(f"- Critical gaps (>2x interval): `{sampling.get('critical_gap_count', 0)}`\n")
        f.write(f"- Maximum gap: `{sampling.get('max_gap_sec', 0)}` seconds\n")
        if sampling.get("first_run_ts"):
            f.write(f"- First run in window: `{sampling.get('first_run_ts')}`\n")
        if sampling.get("last_run_ts"):
            f.write(f"- Last run in window: `{sampling.get('last_run_ts')}`\n")

        if gaps:
            f.write("\n## Largest Gaps (Top 5)\n")
            for row in gaps:
                f.write(
                    f"- {row.get('prev_run_ts')} -> {row.get('run_ts')}: `{row.get('gap_sec')}` sec "
                    f"(prev `{row.get('prev_run_id')}` -> curr `{row.get('run_id')}`)\n"
                )

        if uncertainty:
            f.write("\n## Uncertainty\n")
            f.write(f"- Overall evidence level: `{uncertainty.get('overall_evidence_level', 'low')}`\n")
            f.write(f"- Sample size total: `{uncertainty.get('sample_size_total', 0)}`\n")
            for row in risk_quantiles:
                f.write(
                    f"- {row.get('line')} ({row.get('mode')}, hour {row.get('hour_cph')}): "
                    f"P95=`{row.get('point_estimate_sec')}`s, "
                    f"CI=`[{row.get('interval_low_sec')}, {row.get('interval_high_sec')}]`, "
                    f"evidence=`{row.get('evidence_level')}`, n=`{row.get('sample_size')}`\n"
                )
            if not risk_quantiles:
                for row in delay_bands:
                    f.write(
                        f"- {row.get('line')}: P95=`{row.get('point_estimate_sec')}`s, "
                        f"band=`[{row.get('interval_low_sec')}, {row.get('interval_high_sec')}]`, "
                        f"evidence=`{row.get('evidence_level')}`, n=`{row.get('sample_size')}`\n"
                    )

        f.write("\n## Top Lines by P95 Delay\n")
        for row in top_lines:
            f.write(
                f"- {row.get('line')}: P50={row.get('p50_delay_sec')}s, "
                f"P90={row.get('p90_delay_sec')}s, P95={row.get('p95_delay_sec')}s, n={row.get('n')}\n"
            )

    print(out_path)


if __name__ == "__main__":
    main()
