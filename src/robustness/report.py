from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from src.common.io import write_csv


def summarize(path: Path) -> list[dict]:
    grouped: dict[tuple[str, int], list[float]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            grouped[(r["strategy"], int(r["k_pct"]))].append(float(r["lcc_ratio"]))

    rows: list[dict] = []
    for (strategy, k_pct), vals in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
        rows.append(
            {
                "strategy": strategy,
                "k_pct": k_pct,
                "lcc_ratio_avg": round(sum(vals) / len(vals), 6),
                "runs": len(vals),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize robustness runs")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", default="data/robustness/latest/robustness_summary.csv")
    args = parser.parse_args()

    rows = summarize(Path(args.input))
    write_csv(Path(args.out), rows, ["strategy", "k_pct", "lcc_ratio_avg", "runs"])
    print(args.out)


if __name__ == "__main__":
    main()
