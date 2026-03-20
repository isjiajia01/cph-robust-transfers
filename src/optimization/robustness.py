from __future__ import annotations

"""Bridge module exposing robustness simulation/report entry points under src/optimization."""

def simulate_failures_main():
    from src.robustness.simulate_failures import main

    return main()


def report_main():
    from src.robustness.report import main

    return main()


def week2_report_main():
    from src.robustness.week2_report import main

    return main()

__all__ = [
    "simulate_failures_main",
    "report_main",
    "week2_report_main",
]
