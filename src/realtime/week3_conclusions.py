from __future__ import annotations

import argparse
import csv
import io
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _query_rows(project_id: str, bq_location: str, sql: str) -> list[dict]:
    try:
        from google.cloud import bigquery  # type: ignore

        client = bigquery.Client(project=project_id, location=bq_location)
        rows = client.query(sql).result()
        return [{k: r[k] for k in r.keys()} for r in rows]
    except ModuleNotFoundError:
        cmd = [
            "bq",
            f"--project_id={project_id}",
            f"--location={bq_location}",
            "query",
            "--nouse_legacy_sql",
            "--format=csv",
            sql,
        ]
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        reader = csv.DictReader(io.StringIO(proc.stdout))
        return [dict(r) for r in reader]


def _hour_dow_sql(project_id: str, dataset: str, days: int) -> str:
    return f"""
WITH base AS (
  SELECT
    line,
    hour_cph,
    dow_cph,
    TIMESTAMP_DIFF(SAFE.TIMESTAMP(realtime_dep_ts), SAFE.TIMESTAMP(planned_dep_ts), SECOND) AS delay_sec
  FROM `{project_id}.{dataset}.departures_enriched`
  WHERE obs_ts_utc_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
    AND SAFE.TIMESTAMP(realtime_dep_ts) IS NOT NULL
    AND SAFE.TIMESTAMP(planned_dep_ts) IS NOT NULL
)
SELECT
  hour_cph,
  dow_cph,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(50)] AS p50_delay_sec,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(90)] AS p90_delay_sec,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(95)] AS p95_delay_sec,
  COUNT(*) AS n
FROM base
GROUP BY hour_cph, dow_cph
ORDER BY dow_cph, hour_cph
"""


def _line_reliability_sql(project_id: str, dataset: str, days: int, min_n: int) -> str:
    return f"""
WITH base AS (
  SELECT
    line,
    TIMESTAMP_DIFF(SAFE.TIMESTAMP(realtime_dep_ts), SAFE.TIMESTAMP(planned_dep_ts), SECOND) AS delay_sec
  FROM `{project_id}.{dataset}.departures_enriched`
  WHERE obs_ts_utc_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
    AND SAFE.TIMESTAMP(realtime_dep_ts) IS NOT NULL
    AND SAFE.TIMESTAMP(planned_dep_ts) IS NOT NULL
)
SELECT
  line,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(50)] AS p50_delay_sec,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(90)] AS p90_delay_sec,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(95)] AS p95_delay_sec,
  AVG(delay_sec) AS avg_delay_sec,
  COUNT(*) AS n
FROM base
GROUP BY line
HAVING COUNT(*) >= {min_n}
ORDER BY p95_delay_sec ASC, avg_delay_sec ASC, n DESC
"""


def _plot_hour(hour_rows: list[dict], out_path: Path) -> None:
    by_hour: dict[int, list[int]] = {}
    for r in hour_rows:
        h = int(r.get("hour_cph") or 0)
        by_hour.setdefault(h, []).append(int(r.get("p95_delay_sec") or 0))
    xs = sorted(by_hour)
    ys = [int(round(sum(by_hour[h]) / len(by_hour[h]))) for h in xs]

    plt.figure(figsize=(10, 4.5))
    plt.plot(xs, ys, marker="o", color="#2f6db3")
    plt.xlabel("Hour (Europe/Copenhagen)")
    plt.ylabel("P95 delay (sec)")
    plt.title("Week3: P95 Delay by Hour (CPH)")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()


def _plot_dow(hour_rows: list[dict], out_path: Path) -> None:
    names = {1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"}
    by_dow: dict[int, list[int]] = {}
    for r in hour_rows:
        d = int(r.get("dow_cph") or 0)
        by_dow.setdefault(d, []).append(int(r.get("p95_delay_sec") or 0))
    xs = sorted(by_dow)
    ys = [int(round(sum(by_dow[d]) / len(by_dow[d]))) for d in xs]
    labels = [names.get(d, str(d)) for d in xs]

    plt.figure(figsize=(9, 4.5))
    plt.bar(labels, ys, color="#c75b39", alpha=0.85)
    plt.xlabel("Day of week (CPH)")
    plt.ylabel("P95 delay (sec)")
    plt.title("Week3: P95 Delay by Day of Week (CPH)")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()


def _plot_line_rank(line_rows: list[dict], out_path: Path, top_k: int) -> None:
    worst = sorted(line_rows, key=lambda r: int(r.get("p95_delay_sec") or 0), reverse=True)[:top_k]
    labels = [str(r.get("line") or "UNKNOWN")[:24] for r in worst]
    vals = [int(r.get("p95_delay_sec") or 0) for r in worst]

    plt.figure(figsize=(12, 5))
    plt.bar(range(len(worst)), vals, color="#8a9a5b")
    plt.xticks(range(len(worst)), labels, rotation=35, ha="right")
    plt.ylabel("P95 delay (sec)")
    plt.title("Week3: Worst Lines by P95 Delay")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()


def _write_md(path: Path, hour_rows: list[dict], line_rows: list[dict], router_csv: str, risk_csv: str, days: int) -> None:
    total_n = sum(int(r.get("n") or 0) for r in line_rows)
    best = line_rows[:10]
    worst = sorted(line_rows, key=lambda r: int(r.get("p95_delay_sec") or 0), reverse=True)[:10]
    risk_rows: list[dict[str, str]] = []
    risk_path = Path(risk_csv)
    if risk_path.exists():
        with risk_path.open("r", encoding="utf-8", newline="") as f:
            risk_rows = list(csv.DictReader(f))
    top_uncertain = sorted(risk_rows, key=lambda r: int(r.get("p95_delay_sec") or 0), reverse=True)[:5]

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("# Week3 Conclusions (Preliminary)\n\n")
        f.write(f"- Window: last `{days}` day(s) from BigQuery `departures_enriched`\n")
        f.write(f"- Effective observations across ranked lines: `{total_n}`\n")
        f.write("- Timezone: `Europe/Copenhagen` (`hour_cph`, `dow_cph`)\n\n")
        f.write("## Reliability Ranking (Best P95 Delay)\n")
        for r in best:
            f.write(
                f"- {r.get('line')}: P50={int(r.get('p50_delay_sec') or 0)}s, "
                f"P90={int(r.get('p90_delay_sec') or 0)}s, "
                f"P95={int(r.get('p95_delay_sec') or 0)}s, n={int(r.get('n') or 0)}\n"
            )
        f.write("\n## Reliability Ranking (Worst P95 Delay)\n")
        for r in worst:
            f.write(
                f"- {r.get('line')}: P50={int(r.get('p50_delay_sec') or 0)}s, "
                f"P90={int(r.get('p90_delay_sec') or 0)}s, "
                f"P95={int(r.get('p95_delay_sec') or 0)}s, n={int(r.get('n') or 0)}\n"
            )
        f.write("\n## Uncertainty\n")
        if top_uncertain:
            for r in top_uncertain:
                f.write(
                    f"- {r.get('line')} ({r.get('mode')}, hour {r.get('hour_cph')}): "
                    f"P95={int(r.get('p95_delay_sec') or 0)}s, "
                    f"CI=[{int(r.get('p95_ci_low') or 0)}, {int(r.get('p95_ci_high') or 0)}], "
                    f"evidence={r.get('evidence_level')}, n={int(r.get('sample_size_effective') or 0)}\n"
                )
        else:
            f.write("- No local risk-model uncertainty file available.\n")
        f.write("\n## Outputs\n")
        f.write("- `docs/figures/week3_p95_by_hour_cph.png`\n")
        f.write("- `docs/figures/week3_p95_by_dow_cph.png`\n")
        f.write("- `docs/figures/week3_line_reliability_rank.png`\n")
        f.write("- `data/analysis/week3_hour_dow_quantiles.csv`\n")
        f.write("- `data/analysis/week3_line_reliability_rank.csv`\n")
        f.write(f"- Pareto table: `{router_csv}`\n")
        f.write(f"- Risk model table: `{risk_csv}`\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Week3 conclusion artifacts from BigQuery")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--dataset", default="cph_rt")
    parser.add_argument("--bq-location", default="europe-north1")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--min-line-n", type=int, default=20)
    parser.add_argument("--hour-dow-out", default="data/analysis/week3_hour_dow_quantiles.csv")
    parser.add_argument("--line-rank-out", default="data/analysis/week3_line_reliability_rank.csv")
    parser.add_argument("--fig-hour", default="docs/figures/week3_p95_by_hour_cph.png")
    parser.add_argument("--fig-dow", default="docs/figures/week3_p95_by_dow_cph.png")
    parser.add_argument("--fig-line", default="docs/figures/week3_line_reliability_rank.png")
    parser.add_argument("--out-md", default="docs/week3_conclusions.md")
    parser.add_argument("--router-csv", default="data/analysis/router_pareto_table.csv")
    parser.add_argument("--risk-csv", default="data/analysis/risk_model_mode_level.csv")
    args = parser.parse_args()

    hour_rows = _query_rows(args.project_id, args.bq_location, _hour_dow_sql(args.project_id, args.dataset, args.days))
    line_rows = _query_rows(
        args.project_id,
        args.bq_location,
        _line_reliability_sql(args.project_id, args.dataset, args.days, args.min_line_n),
    )

    if not line_rows:
        raise SystemExit("No line reliability rows. Increase window or lower --min-line-n.")

    _write_csv(Path(args.hour_dow_out), hour_rows, ["hour_cph", "dow_cph", "p50_delay_sec", "p90_delay_sec", "p95_delay_sec", "n"])
    _write_csv(Path(args.line_rank_out), line_rows, ["line", "p50_delay_sec", "p90_delay_sec", "p95_delay_sec", "avg_delay_sec", "n"])

    _plot_hour(hour_rows, Path(args.fig_hour))
    _plot_dow(hour_rows, Path(args.fig_dow))
    _plot_line_rank(line_rows, Path(args.fig_line), top_k=20)

    _write_md(Path(args.out_md), hour_rows, line_rows, args.router_csv, args.risk_csv, args.days)

    print(args.hour_dow_out)
    print(args.line_rank_out)
    print(args.fig_hour)
    print(args.fig_dow)
    print(args.fig_line)
    print(args.out_md)


if __name__ == "__main__":
    main()
