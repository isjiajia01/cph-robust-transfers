from __future__ import annotations

import argparse
import inspect
import sys
from collections.abc import Callable
from contextlib import contextmanager

from src.app import realtime_pipeline, results_dashboard, static_pipeline
from src.accessibility import server as accessibility_server
from src.benchmark import cli as benchmark_cli
from src.optimization import api as optimization_api


@contextmanager
def _patched_argv(argv: list[str]):
    original = sys.argv[:]
    sys.argv = [original[0], *argv]
    try:
        yield
    finally:
        sys.argv = original


def _dispatch(main_fn: Callable[..., object], argv: list[str], argv_for_zero_arg: list[str] | None = None) -> int:
    if len(inspect.signature(main_fn).parameters) > 0:
        return int(main_fn(argv))
    with _patched_argv(argv_for_zero_arg or argv):
        result = main_fn()
    return int(result) if result is not None else 0


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
        "accessibility": lambda sub_argv: accessibility_server.main(["serve", *sub_argv]),
        "report": lambda: results_dashboard.main(rest),
        "benchmark": lambda sub_argv: benchmark_cli.main(sub_argv),
    }

    zero_arg_passthrough = {
        "ingest": ["--help"] if not rest else rest,
        "graph": ["--help"] if not rest else rest,
        "realtime": ["--help"] if not rest else rest,
        "risk": ["--help"] if not rest else rest,
        "report": rest,
    }
    return _dispatch(command_map[args.command], rest, argv_for_zero_arg=zero_arg_passthrough.get(args.command))


if __name__ == "__main__":
    raise SystemExit(main())
