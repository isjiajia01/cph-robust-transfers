from __future__ import annotations

import argparse
from collections.abc import Callable


def _dispatch(main_fn: Callable[[], object]) -> int:
    main_fn()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Template-aligned application CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("accessibility-server", help="Run the accessibility proxy and static frontend")
    subparsers.add_parser("accessibility-build-static", help="Validate accessibility frontend assets")
    subparsers.add_parser("gtfs-download", help="Run GTFS download pipeline entry point")
    subparsers.add_parser("gtfs-parse", help="Run GTFS parse pipeline entry point")
    subparsers.add_parser("graph-build", help="Run graph build entry point")
    subparsers.add_parser("graph-metrics", help="Run graph metrics entry point")
    subparsers.add_parser("week1-report", help="Run static-network reporting entry point")
    subparsers.add_parser("realtime-collector", help="Run realtime collector entry point")
    subparsers.add_parser("task-a-daily", help="Run daily quality/report entry point")
    subparsers.add_parser("week3-summary", help="Run week3 markdown/json summary entry point")
    subparsers.add_parser("week3-conclusions", help="Run week3 conclusions entry point")
    subparsers.add_parser("results-dashboard", help="Render a static research-results dashboard")
    return parser


def main(argv: list[str] | None = None) -> int:
    from src.app import accessibility_pipeline, realtime_pipeline, results_dashboard, static_pipeline

    parser = build_parser()
    args = parser.parse_args(argv)

    command_map: dict[str, Callable[[], object]] = {
        "accessibility-server": accessibility_pipeline.accessibility_server_main,
        "accessibility-build-static": accessibility_pipeline.accessibility_build_static_main,
        "gtfs-download": static_pipeline.gtfs_download_main,
        "gtfs-parse": static_pipeline.gtfs_parse_main,
        "graph-build": static_pipeline.build_graph_main,
        "graph-metrics": static_pipeline.graph_metrics_main,
        "week1-report": static_pipeline.week1_report_main,
        "realtime-collector": realtime_pipeline.collector_main,
        "task-a-daily": realtime_pipeline.task_a_main,
        "week3-summary": realtime_pipeline.summary_main,
        "week3-conclusions": realtime_pipeline.conclusions_main,
        "results-dashboard": lambda: results_dashboard.main([]),
    }
    return _dispatch(command_map[args.command])


if __name__ == "__main__":
    raise SystemExit(main())
