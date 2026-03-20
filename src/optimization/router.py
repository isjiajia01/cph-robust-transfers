from __future__ import annotations

"""Bridge module exposing the current router implementation under src/optimization."""

from src.robustness.router import run_router


def main():
    from src.robustness.router import main as _main

    return _main()

__all__ = ["run_router", "main"]
