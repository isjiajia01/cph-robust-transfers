from __future__ import annotations

import argparse
from collections.abc import Callable


def _dispatch(main_fn: Callable[[], object]) -> int:
    main_fn()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Public mobility resilience site CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve-site", help="Run the public mobility resilience site")
    subparsers.add_parser("build-site", help="Validate public site assets")
    subparsers.add_parser("build-atlas", help="Build the precomputed mobility resilience atlas bundle")
    subparsers.add_parser("generate-origins", help="Generate expanded atlas origins from seed stations")
    subparsers.add_parser("benchmark-dashboard", help="Render a static benchmark dashboard")
    subparsers.add_parser("results-dashboard", help="Render a static research-results dashboard")
    return parser


def main(argv: list[str] | None = None) -> int:
    from src.accessibility import generate_origins, server
    from src.app import benchmark_dashboard, results_dashboard

    parser = build_parser()
    args = parser.parse_args(argv)

    command_map: dict[str, Callable[[], object]] = {
        "serve-site": lambda: server.main(["serve"]),
        "build-site": lambda: server.main(["build-static"]),
        "build-atlas": lambda: server.main(["build-atlas"]),
        "generate-origins": lambda: generate_origins.main([]),
        "benchmark-dashboard": lambda: benchmark_dashboard.main([]),
        "results-dashboard": lambda: results_dashboard.main([]),
    }
    return _dispatch(command_map[args.command])


if __name__ == "__main__":
    raise SystemExit(main())
