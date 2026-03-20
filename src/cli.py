from __future__ import annotations

import argparse
from collections.abc import Callable

from src.app import accessibility_pipeline, realtime_pipeline, results_dashboard, static_pipeline
from src.benchmark import cli as benchmark_cli
from src.optimization import api as optimization_api


def _dispatch(main_fn: Callable[[list[str]], int] | Callable[[], object], argv: list[str]) -> int:
    try:
        return int(main_fn(argv))  # type: ignore[arg-type]
    except TypeError:
        main_fn()  # type: ignore[misc]
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified CLI for reliability-aware accessibility and routing workflows"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("ingest", "graph", "realtime", "risk", "accessibility", "report", "benchmark"):
        subparsers.add_parser(name)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, rest = parser.parse_known_args(argv)

    command_map: dict[str, Callable[[list[str]], int] | Callable[[], object]] = {
        "ingest": static_pipeline.gtfs_download_main,
        "graph": static_pipeline.build_graph_main,
        "realtime": realtime_pipeline.collector_main,
        "risk": optimization_api.run_risk_model_cli,
        "accessibility": accessibility_pipeline.accessibility_server_main,
        "report": lambda: results_dashboard.main(rest),
        "benchmark": lambda sub_argv: benchmark_cli.main(sub_argv),
    }

    return _dispatch(command_map[args.command], rest)


if __name__ == "__main__":
    raise SystemExit(main())
