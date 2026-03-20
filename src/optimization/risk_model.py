from __future__ import annotations

"""Bridge module exposing the current risk-model implementation under src/optimization."""

from src.robustness.risk_model import ModeLevelRiskModel, RiskEstimate


def main():
    from src.robustness.risk_model import main as _main

    return _main()

__all__ = ["ModeLevelRiskModel", "RiskEstimate", "main"]
