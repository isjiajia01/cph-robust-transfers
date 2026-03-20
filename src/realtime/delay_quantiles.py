from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from src.common.io import write_csv


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _percentile(sorted_values: list[int], p: float) -> int:
    if not sorted_values:
        return 0
    idx = int(round((p / 100.0) * (len(sorted_values) - 1)))
    idx = max(0, min(len(sorted_values) - 1, idx))
    return sorted_values[idx]


def compute_quantiles(input_csv: Path) -> list[dict]:
    per_line: dict[str, list[int]] = defaultdict(list)

    with input_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            planned = _parse_ts(r.get("planned_dep_ts"))
            realtime = _parse_ts(r.get("realtime_dep_ts"))
            line = (r.get("line") or "UNKNOWN").strip() or "UNKNOWN"
            if not planned or not realtime:
                continue
            delay = int((realtime - planned).total_seconds())
            per_line[line].append(delay)

    rows: list[dict] = []
    for line, values in sorted(per_line.items(), key=lambda x: x[0]):
        vals = sorted(values)
        rows.append(
            {
                "line": line,
                "p50_delay_sec": _percentile(vals, 50),
                "p90_delay_sec": _percentile(vals, 90),
                "p95_delay_sec": _percentile(vals, 95),
                "n": len(vals),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute delay quantiles from departures.csv")
    parser.add_argument("--input", required=True, help="departures.csv path")
    parser.add_argument("--out", default="data/analysis/delay_quantiles.csv")
    args = parser.parse_args()

    rows = compute_quantiles(Path(args.input))
    write_csv(Path(args.out), rows, ["line", "p50_delay_sec", "p90_delay_sec", "p95_delay_sec", "n"])
    print(args.out)


if __name__ == "__main__":
    main()
