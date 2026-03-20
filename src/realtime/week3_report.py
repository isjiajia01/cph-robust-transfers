from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _read_departures(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _quantile(vals: list[int], q: float) -> int:
    if not vals:
        return 0
    s = sorted(vals)
    idx = int(round((q / 100.0) * (len(s) - 1)))
    idx = max(0, min(len(s) - 1, idx))
    return s[idx]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Week3 delay quantile figures and summary")
    parser.add_argument("--departures", required=True)
    parser.add_argument("--fig-line", default="docs/figures/week3_delay_quantiles_by_line.png")
    parser.add_argument("--fig-hour", default="docs/figures/week3_delay_p95_by_hour.png")
    parser.add_argument("--summary", default="docs/week3_summary.md")
    parser.add_argument("--top-k", type=int, default=12)
    args = parser.parse_args()

    rows = _read_departures(Path(args.departures))
    by_line: dict[str, list[int]] = defaultdict(list)
    by_hour: dict[int, list[int]] = defaultdict(list)

    for r in rows:
        p = _parse_iso(r.get("planned_dep_ts"))
        rt = _parse_iso(r.get("realtime_dep_ts"))
        if not p or not rt:
            continue
        d = int((rt - p).total_seconds())
        line = (r.get("line") or "UNKNOWN").strip() or "UNKNOWN"
        by_line[line].append(d)
        by_hour[p.hour].append(d)

    if not by_line:
        raise SystemExit("No delay rows with planned/realtime timestamps")

    line_stats = []
    for line, vals in by_line.items():
        line_stats.append(
            {
                "line": line,
                "p50": _quantile(vals, 50),
                "p90": _quantile(vals, 90),
                "p95": _quantile(vals, 95),
                "n": len(vals),
            }
        )
    line_stats.sort(key=lambda x: x["p95"], reverse=True)

    top = line_stats[: args.top_k]
    labels = [r["line"][:24] for r in top]
    p50 = [r["p50"] for r in top]
    p95 = [r["p95"] for r in top]

    x = range(len(top))
    plt.figure(figsize=(12, 5))
    plt.bar(x, p95, color="#c75b39", alpha=0.85, label="P95")
    plt.plot(x, p50, color="#2f6db3", marker="o", label="P50")
    plt.xticks(list(x), labels, rotation=35, ha="right")
    plt.ylabel("Delay (sec)")
    plt.title("Week3: Delay Quantiles by Line")
    plt.legend()
    plt.tight_layout()
    Path(args.fig_line).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.fig_line, dpi=150)
    plt.close()

    hour_stats = sorted((h, _quantile(v, 95), len(v)) for h, v in by_hour.items())
    hx = [h for h, _, _ in hour_stats]
    hy = [v for _, v, _ in hour_stats]

    plt.figure(figsize=(10, 4.5))
    plt.plot(hx, hy, marker="o", color="#2f6db3")
    plt.xlabel("Hour of day")
    plt.ylabel("P95 delay (sec)")
    plt.title("Week3: P95 Delay by Planned Departure Hour")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(args.fig_hour, dpi=150)
    plt.close()

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        f.write("# Week3 Summary\n\n")
        f.write(f"- Source departures file: `{args.departures}`\n")
        f.write(f"- Delay observations (planned+realtime available): {sum(r['n'] for r in line_stats)}\n")
        f.write("\n## Top lines by P95 delay\n")
        for r in top[:10]:
            f.write(f"- {r['line']}: P50={r['p50']}s, P90={r['p90']}s, P95={r['p95']}s, n={r['n']}\n")
        f.write("\n## Figures\n")
        f.write(f"- `{args.fig_line}`\n")
        f.write(f"- `{args.fig_hour}`\n")

    print(summary_path)
    print(args.fig_line)
    print(args.fig_hour)


if __name__ == "__main__":
    main()
