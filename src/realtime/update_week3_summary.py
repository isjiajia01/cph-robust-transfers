from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _int_or_zero(v: str | None) -> int:
    if not v:
        return 0
    try:
        return int(float(v))
    except ValueError:
        return 0


def _float_or_zero(v: str | None) -> float:
    if not v:
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def _load_integrity(path: Path) -> dict[str, str]:
    rows = _read_csv_rows(path)
    return rows[0] if rows else {}


def _load_quantiles(path: Path) -> list[dict[str, str]]:
    rows = _read_csv_rows(path)
    rows.sort(key=lambda r: _int_or_zero(r.get("p95_delay_sec")), reverse=True)
    return rows


def _to_summary_dict(
    *,
    quantiles: list[dict[str, str]],
    integrity: dict[str, str],
    gaps: list[dict[str, str]],
    project_id: str,
    dataset: str,
    quantiles_path: str,
    integrity_path: str,
) -> dict:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    coverage = _float_or_zero(integrity.get("run_coverage_ratio"))
    run_count = _int_or_zero(integrity.get("run_count_24h"))
    expected_runs = _int_or_zero(integrity.get("expected_runs_24h"))
    warning_gaps = _int_or_zero(integrity.get("warning_gap_count"))
    critical_gaps = _int_or_zero(integrity.get("critical_gap_count"))
    max_gap = _int_or_zero(integrity.get("max_gap_sec"))

    top_lines = []
    for row in quantiles:
        top_lines.append(
            {
                "line": row.get("line"),
                "p50_delay_sec": _int_or_zero(row.get("p50_delay_sec")),
                "p90_delay_sec": _int_or_zero(row.get("p90_delay_sec")),
                "p95_delay_sec": _int_or_zero(row.get("p95_delay_sec")),
                "n": _int_or_zero(row.get("n")),
            }
        )

    largest_gaps = []
    for row in gaps:
        largest_gaps.append(
            {
                "prev_run_id": row.get("prev_run_id"),
                "prev_run_ts": row.get("prev_run_ts"),
                "run_id": row.get("run_id"),
                "run_ts": row.get("run_ts"),
                "gap_sec": _int_or_zero(row.get("gap_sec")),
            }
        )

    return {
        "generated_at_utc": generated_at,
        "source": {"project_id": project_id, "dataset": dataset},
        "inputs": {"quantiles_csv": quantiles_path, "integrity_csv": integrity_path},
        "sampling_24h": {
            "run_count_24h": run_count,
            "expected_runs_24h": expected_runs,
            "coverage_ratio": coverage,
            "warning_gap_count": warning_gaps,
            "critical_gap_count": critical_gaps,
            "max_gap_sec": max_gap,
            "first_run_ts": integrity.get("first_run_ts"),
            "last_run_ts": integrity.get("last_run_ts"),
            "largest_gaps": largest_gaps,
        },
        "top_lines_by_p95": top_lines,
    }


def _write_markdown(path: Path, summary: dict, top_k: int) -> None:
    sampling = summary["sampling_24h"]
    top_lines = summary["top_lines_by_p95"][:top_k]
    largest_gaps = sampling["largest_gaps"][:5]

    with path.open("w", encoding="utf-8") as f:
        f.write("# Week3 Summary\n\n")
        f.write(f"- Generated (UTC): `{summary['generated_at_utc']}`\n")
        f.write(f"- Source: BigQuery `{summary['source']['project_id']}.{summary['source']['dataset']}`\n")
        f.write(f"- Quantiles CSV: `{summary['inputs']['quantiles_csv']}`\n")
        f.write(f"- Integrity CSV: `{summary['inputs']['integrity_csv']}`\n")
        f.write("\n## 24h Sampling Integrity\n")
        f.write(
            f"- Runs observed: `{sampling['run_count_24h']}` / expected "
            f"`{sampling['expected_runs_24h']}` (coverage `{sampling['coverage_ratio']:.2%}`)\n"
        )
        f.write(f"- Gap warnings (>1.5x interval): `{sampling['warning_gap_count']}`\n")
        f.write(f"- Critical gaps (>2x interval): `{sampling['critical_gap_count']}`\n")
        f.write(f"- Maximum gap: `{sampling['max_gap_sec']}` seconds\n")
        if sampling.get("first_run_ts"):
            f.write(f"- First run in window: `{sampling['first_run_ts']}`\n")
        if sampling.get("last_run_ts"):
            f.write(f"- Last run in window: `{sampling['last_run_ts']}`\n")

        if largest_gaps:
            f.write("\n## Largest Gaps (Top 5)\n")
            for row in largest_gaps:
                f.write(
                    f"- {row.get('prev_run_ts')} -> {row.get('run_ts')}: `{row.get('gap_sec')}` sec "
                    f"(prev `{row.get('prev_run_id')}` -> curr `{row.get('run_id')}`)\n"
                )

        f.write("\n## Top Lines by P95 Delay\n")
        for row in top_lines:
            f.write(
                f"- {row.get('line')}: P50={row.get('p50_delay_sec')}s, "
                f"P90={row.get('p90_delay_sec')}s, P95={row.get('p95_delay_sec')}s, n={row.get('n')}\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Update docs/week3_summary.md from BQ exports")
    parser.add_argument("--quantiles", required=True, help="CSV from run_delay_quantiles.sh")
    parser.add_argument("--integrity", required=True, help="CSV from check_sampling_integrity_24h.sh")
    parser.add_argument("--gaps", required=True, help="Gap CSV from check_sampling_integrity_24h.sh")
    parser.add_argument("--out", default="docs/week3_summary.md")
    parser.add_argument("--json-out", default="", help="Optional JSON output path for machine-readable summary")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--dataset", default="cph_rt")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    quantiles = _load_quantiles(Path(args.quantiles))
    integrity = _load_integrity(Path(args.integrity))
    gaps = _read_csv_rows(Path(args.gaps))

    summary = _to_summary_dict(
        quantiles=quantiles,
        integrity=integrity,
        gaps=gaps,
        project_id=args.project_id,
        dataset=args.dataset,
        quantiles_path=args.quantiles,
        integrity_path=args.integrity,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_markdown(out_path, summary, args.top_k)

    print(out_path)
    if args.json_out:
        json_out_path = Path(args.json_out)
        json_out_path.parent.mkdir(parents=True, exist_ok=True)
        with json_out_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=True, indent=2)
        print(json_out_path)


if __name__ == "__main__":
    main()
