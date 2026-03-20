from __future__ import annotations

"""Unified template-style API surface for optimization/research entry points."""

from src.robustness.risk_model import ModeLevelRiskModel, RiskEstimate, RiskModel
from src.robustness.router import RouterConfig, run_router


def get_risk_model_class():
    return ModeLevelRiskModel


def get_risk_estimate_class():
    return RiskEstimate


def run_risk_model_cli():
    from src.robustness.risk_model import main

    return main()


def run_router_cli():
    from src.robustness.router import main

    return main()


def run_robustness_simulation_cli():
    from src.robustness.simulate_failures import main

    return main()


def run_robustness_report_cli():
    from src.robustness.report import main

    return main()


def run_week2_report_cli():
    from src.robustness.week2_report import main

    return main()


__all__ = [
    "RiskModel",
    "ModeLevelRiskModel",
    "RiskEstimate",
    "RouterConfig",
    "run_router",
    "get_risk_model_class",
    "get_risk_estimate_class",
    "run_risk_model_cli",
    "run_router_cli",
    "run_robustness_simulation_cli",
    "run_robustness_report_cli",
    "run_week2_report_cli",
]
