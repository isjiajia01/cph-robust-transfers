from __future__ import annotations

"""Template-aligned bridge for the realtime collection/reporting application layer."""

def collector_main():
    from src.realtime.collector import main

    return main()


def task_a_main():
    from src.realtime.task_a_daily_job import main

    return main()


def summary_main():
    from src.realtime.update_week3_summary import main

    return main()


def conclusions_main():
    from src.realtime.week3_conclusions import main

    return main()

__all__ = [
    "collector_main",
    "task_a_main",
    "summary_main",
    "conclusions_main",
]
