from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark scaffolding for scheduled, realtime-snapshot, and robust comparisons"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a benchmark manifest scaffold")
    init_parser.add_argument(
        "--out",
        default="results/benchmark/latest/manifest.md",
        help="Path to the benchmark manifest scaffold",
    )
    return parser


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return init_manifest(Path(args.out))
    raise SystemExit(f"Unknown benchmark command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
