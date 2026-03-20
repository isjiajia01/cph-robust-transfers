from __future__ import annotations

import argparse
from collections.abc import Callable

from src.optimization import api


def _dispatch(main_fn: Callable[[], object]) -> int:
    main_fn()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Template-aligned optimization CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("risk-model", help="Run the risk-model CLI")
    subparsers.add_parser("router", help="Run the router CLI")
    subparsers.add_parser("robustness-sim", help="Run robustness simulation CLI")
    subparsers.add_parser("robustness-report", help="Run robustness report CLI")
    subparsers.add_parser("week2-report", help="Run week2 report CLI")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command_map: dict[str, Callable[[], object]] = {
        "risk-model": api.run_risk_model_cli,
        "router": api.run_router_cli,
        "robustness-sim": api.run_robustness_simulation_cli,
        "robustness-report": api.run_robustness_report_cli,
        "week2-report": api.run_week2_report_cli,
    }
    return _dispatch(command_map[args.command])


if __name__ == "__main__":
    raise SystemExit(main())
