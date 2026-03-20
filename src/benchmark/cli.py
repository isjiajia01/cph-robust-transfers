from __future__ import annotations

import argparse
import csv
from pathlib import Path

from src.robustness.risk_model import ModeLevelRiskModel
from src.robustness.router import RouterConfig, run_router


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark tooling for scheduled, realtime-snapshot, and robust comparisons"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a benchmark manifest scaffold")
    init_parser.add_argument(
        "--out",
        default="results/benchmark/latest/manifest.md",
        help="Path to the benchmark manifest scaffold",
    )

    compare_parser = subparsers.add_parser(
        "compare",
        help="Build a minimal baseline comparison table from departures and route candidates",
    )
    compare_parser.add_argument("--departures", required=True, help="departures.csv for empirical risk fitting")
    compare_parser.add_argument("--candidates", required=True, help="candidate paths csv")
    compare_parser.add_argument("--out", default="results/benchmark/latest/comparison.csv")
    compare_parser.add_argument("--threshold-min", type=float, default=45.0)
    compare_parser.add_argument("--n-mode-hour-min", type=int, default=200)
    compare_parser.add_argument("--n-mode-min", type=int, default=500)
    compare_parser.add_argument("--bootstrap-iters", type=int, default=1000)
    compare_parser.add_argument("--seed", type=int, default=42)
    return parser


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def init_manifest(out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "\n".join(
            [
                "# Benchmark Manifest",
                "",
                "## Scope",
                "- scheduled-only baseline",
                "- realtime snapshot baseline",
                "- robust / risk-aware baseline",
                "",
                "## Required Metrics",
                "- expected arrival time",
                "- p90 arrival time",
                "- p95 arrival time",
                "- missed-transfer rate",
                "- regret",
                "- reachable opportunities within T minutes",
                "- accessibility loss",
                "",
                "## Versioning",
                "- git_sha =",
                "- gtfs_version =",
                "- collection_window =",
                "- risk_model_version =",
                "- parameter_hash =",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"wrote_benchmark_manifest={out_path}")
    return 0


def _safe_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except ValueError:
        return default


def build_comparison_rows(
    departures: list[dict[str, str]],
    candidates: list[dict[str, str]],
    *,
    threshold_min: float,
    n_mode_hour_min: int,
    n_mode_min: int,
    bootstrap_iters: int,
    seed: int,
) -> list[dict[str, object]]:
    model = ModeLevelRiskModel(
        departures,
        n_mode_hour_min=n_mode_hour_min,
        n_mode_min=n_mode_min,
        bootstrap_iters=bootstrap_iters,
        seed=seed,
    )
    router_rows = run_router(candidates, model, RouterConfig())

    comparison_rows: list[dict[str, object]] = []
    for row in router_rows:
        travel_time = float(row["travel_time_min"])
        p50_delay_min = max(0.0, float(row["p50_delay_sec"]) / 60.0)
        p90_delay_min = max(0.0, float(row["p90_delay_sec"]) / 60.0)
        miss_prob = float(row["miss_prob"])

        scheduled_eta = round(travel_time, 4)
        snapshot_eta = round(travel_time + p50_delay_min, 4)
        robust_eta = round(travel_time + p90_delay_min, 4)

        comparison_rows.append(
            {
                "od_id": row["od_id"],
                "path_id": row["path_id"],
                "depart_ts_cph": row["depart_ts_cph"],
                "line": next((c.get("line", "") for c in candidates if c.get("od_id") == row["od_id"] and c.get("path_id") == row["path_id"]), ""),
                "mode": next((c.get("mode", "") for c in candidates if c.get("od_id") == row["od_id"] and c.get("path_id") == row["path_id"]), ""),
                "travel_time_min": round(travel_time, 4),
                "scheduled_eta_min": scheduled_eta,
                "snapshot_eta_min": snapshot_eta,
                "robust_eta_min": robust_eta,
                "scheduled_missed_transfer_rate": 0.0,
                "snapshot_missed_transfer_rate": round(miss_prob * 0.5, 6),
                "robust_missed_transfer_rate": round(miss_prob, 6),
                "scheduled_accessible_within_threshold": int(scheduled_eta <= threshold_min),
                "snapshot_accessible_within_threshold": int(snapshot_eta <= threshold_min),
                "robust_accessible_within_threshold": int(robust_eta <= threshold_min),
                "accessibility_loss_flag": int(scheduled_eta <= threshold_min and robust_eta > threshold_min),
                "realtime_snapshot_regret_min": round(max(0.0, snapshot_eta - scheduled_eta), 4),
                "robust_regret_min": round(max(0.0, robust_eta - scheduled_eta), 4),
                "p50_delay_sec": row["p50_delay_sec"],
                "p90_delay_sec": row["p90_delay_sec"],
                "p95_delay_sec": row["p95_delay_sec"],
                "evidence_level": row["evidence_level"],
                "sample_size_effective": row["sample_size_effective"],
                "risk_model_version": row["risk_model_version"],
                "confidence_tag": row["confidence_tag"],
                "source_level": row["source_level"],
                "threshold_min": threshold_min,
            }
        )
    return comparison_rows


def compare(
    departures_path: Path,
    candidates_path: Path,
    out_path: Path,
    *,
    threshold_min: float,
    n_mode_hour_min: int,
    n_mode_min: int,
    bootstrap_iters: int,
    seed: int,
) -> int:
    departures = _read_rows(departures_path)
    candidates = _read_rows(candidates_path)
    rows = build_comparison_rows(
        departures,
        candidates,
        threshold_min=threshold_min,
        n_mode_hour_min=n_mode_hour_min,
        n_mode_min=n_mode_min,
        bootstrap_iters=bootstrap_iters,
        seed=seed,
    )
    _write_rows(
        out_path,
        rows,
        [
            "od_id",
            "path_id",
            "depart_ts_cph",
            "line",
            "mode",
            "travel_time_min",
            "scheduled_eta_min",
            "snapshot_eta_min",
            "robust_eta_min",
            "scheduled_missed_transfer_rate",
            "snapshot_missed_transfer_rate",
            "robust_missed_transfer_rate",
            "scheduled_accessible_within_threshold",
            "snapshot_accessible_within_threshold",
            "robust_accessible_within_threshold",
            "accessibility_loss_flag",
            "realtime_snapshot_regret_min",
            "robust_regret_min",
            "p50_delay_sec",
            "p90_delay_sec",
            "p95_delay_sec",
            "evidence_level",
            "sample_size_effective",
            "risk_model_version",
            "confidence_tag",
            "source_level",
            "threshold_min",
        ],
    )
    print(f"wrote_benchmark_comparison={out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return init_manifest(Path(args.out))
    if args.command == "compare":
        return compare(
            Path(args.departures),
            Path(args.candidates),
            Path(args.out),
            threshold_min=float(args.threshold_min),
            n_mode_hour_min=int(args.n_mode_hour_min),
            n_mode_min=int(args.n_mode_min),
            bootstrap_iters=int(args.bootstrap_iters),
            seed=int(args.seed),
        )
    raise SystemExit(f"Unknown benchmark command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
