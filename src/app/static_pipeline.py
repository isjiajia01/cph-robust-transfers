from __future__ import annotations

"""Template-aligned bridge for static GTFS and graph processing entry points."""

def gtfs_download_main():
    from src.gtfs_ingest.download import main

    return main()


def gtfs_parse_main():
    from src.gtfs_ingest.parse import main

    return main()


def build_graph_main():
    from src.graph.build_stop_graph import main

    return main()


def graph_metrics_main():
    from src.graph.metrics import main

    return main()


def week1_report_main():
    from src.graph.week1_report import main

    return main()

__all__ = [
    "gtfs_download_main",
    "gtfs_parse_main",
    "build_graph_main",
    "graph_metrics_main",
    "week1_report_main",
]
