from __future__ import annotations

import argparse
import json
from pathlib import Path


def _mk_markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": [line + "\n" for line in text.strip().split("\n")]}


def _mk_code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in text.strip().split("\n")],
    }


def build_notebook(base_dir: str) -> dict:
    intro = f"""
# Week2 Robustness Experiments (Auto-Generated)

This notebook is generated from `src.robustness.update_week2_notebook`.

Data source directory:
- `{base_dir}`
"""
    setup = f"""
from pathlib import Path
import pandas as pd
from IPython.display import Image, display

base = Path("{base_dir}")
summary = pd.read_csv(base / "robustness_summary.csv")
critical = pd.read_csv(base / "critical_nodes_top10.csv")

lcc_curve = Path("../docs/figures/week2_random_vs_targeted.png")
extra_curve = Path("../docs/figures/week2_extra_metrics.png")
"""

    notebook = {
        "cells": [
            _mk_markdown(intro),
            _mk_code(setup),
            _mk_markdown("## Random vs Targeted (LCC Curve)"),
            _mk_code("display(Image(filename=str(lcc_curve)))"),
            _mk_markdown("## Extra Metrics (Reachable OD ratio / Avg shortest path)"),
            _mk_code("display(Image(filename=str(extra_curve)))"),
            _mk_markdown("## Robustness Summary"),
            _mk_code("summary.sort_values(['k_pct', 'strategy']).reset_index(drop=True)"),
            _mk_markdown("## Top-10 Critical Nodes"),
            _mk_code("critical"),
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.11",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return notebook


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Week2 robustness notebook from result directory")
    parser.add_argument("--base-dir", default="../data/robustness/20260302_high")
    parser.add_argument("--out", default="notebooks/02_robustness_experiments.ipynb")
    args = parser.parse_args()

    nb = build_notebook(args.base_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
