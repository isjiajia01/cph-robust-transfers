from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _escape(value: object) -> str:
    return html.escape(str(value))


def _avg(rows: list[dict[str, str]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / max(len(rows), 1)


def _count(rows: list[dict[str, str]], key: str) -> int:
    return sum(int(row[key]) for row in rows)


def build_benchmark_html(repo_root: Path, output_path: Path) -> str:
    rows = _load_csv(repo_root / "results" / "benchmark" / "latest" / "comparison.csv")
    if not rows:
        raise ValueError("benchmark comparison is empty")

    total = len(rows)
    scheduled_access = _count(rows, "scheduled_accessible_within_threshold")
    robust_access = _count(rows, "robust_accessible_within_threshold")
    access_loss = _count(rows, "accessibility_loss_flag")
    snapshot_miss = _avg(rows, "snapshot_missed_transfer_rate")
    robust_miss = _avg(rows, "robust_missed_transfer_rate")
    snapshot_regret = _avg(rows, "realtime_snapshot_regret_min")
    robust_regret = _avg(rows, "robust_regret_min")

    top_rows = rows[:12]
    table_rows = "".join(
        "<tr>"
        + "".join(
            f"<td>{_escape(value)}</td>"
            for value in (
                row["od_id"],
                row["line"],
                row["mode"],
                row["scheduled_eta_min"],
                row["snapshot_eta_min"],
                row["robust_eta_min"],
                row["snapshot_missed_transfer_rate"],
                row["robust_missed_transfer_rate"],
                row["accessibility_loss_flag"],
            )
        )
        + "</tr>"
        for row in top_rows
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CPH Benchmark Snapshot</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --ink: #0f1f29;
      --muted: #61717a;
      --panel: rgba(255,255,255,0.88);
      --line: rgba(15,31,41,0.08);
      --teal: #0f766e;
      --amber: #b45309;
      --red: #b91c1c;
      --shadow: 0 26px 70px rgba(15,31,41,0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15,118,110,0.12), transparent 22%),
        linear-gradient(180deg, #faf7f0 0%, var(--bg) 100%);
    }}
    .shell {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 64px;
    }}
    .hero, .section {{
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      border-radius: 28px;
    }}
    .hero {{
      padding: 30px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      margin: 0 0 12px;
      color: var(--teal);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}
    h1, h2 {{
      margin: 0;
      font-family: "Iowan Old Style", Georgia, serif;
      letter-spacing: -0.03em;
    }}
    h1 {{ font-size: clamp(2.6rem, 5vw, 4.4rem); line-height: 0.95; }}
    .hero p {{
      max-width: 70ch;
      color: var(--muted);
      line-height: 1.75;
      margin: 16px 0 0;
    }}
    .nav-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .nav-links a {{
      display: inline-flex;
      align-items: center;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.82);
      color: var(--ink);
      text-decoration: none;
      font-size: 0.92rem;
      font-weight: 600;
    }}
    .section {{
      padding: 24px;
      margin-top: 24px;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .metric-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.94);
      padding: 16px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .metric-value {{
      margin-top: 6px;
      font-size: 1.4rem;
      font-weight: 800;
    }}
    .metric-detail {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .takeaway {{
      margin-top: 18px;
      padding: 18px;
      border-radius: 18px;
      border: 1px solid rgba(15,118,110,0.14);
      background: rgba(15,118,110,0.06);
      line-height: 1.7;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 18px;
      font-size: 0.95rem;
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    code {{
      background: rgba(15,31,41,0.06);
      padding: 2px 6px;
      border-radius: 8px;
    }}
    @media (max-width: 980px) {{
      .metric-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      table {{
        display: block;
        overflow-x: auto;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <p class="eyebrow">Benchmark Snapshot</p>
      <h1>Reliability-Aware Transit Benchmark</h1>
      <p>This page summarizes the current public benchmark slice for <code>cph-robust-transfers</code>. It compares schedule-only, realtime-snapshot, and robust/risk-aware assumptions on a deterministic candidate set derived from observed departures.</p>
      <div class="nav-links">
        <a href="../README.md">README</a>
        <a href="./research_dashboard.html">Research Dashboard</a>
        <a href="../web/accessibility/index.html">Accessibility Prototype</a>
      </div>
      <div class="metric-grid">
        <article class="metric-card">
          <div class="metric-label">Rows Evaluated</div>
          <div class="metric-value">{total}</div>
          <div class="metric-detail">Current deterministic benchmark slice</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Scheduled Access</div>
          <div class="metric-value">{scheduled_access}</div>
          <div class="metric-detail">Reachable within the current threshold on schedule</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Robust Access</div>
          <div class="metric-value">{robust_access}</div>
          <div class="metric-detail">Reachable after reliability penalty is applied</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Access Loss</div>
          <div class="metric-value">{access_loss}</div>
          <div class="metric-detail">Stops pushed out of the threshold by uncertainty</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Snapshot Miss Rate</div>
          <div class="metric-value">{snapshot_miss:.4f}</div>
          <div class="metric-detail">Average realtime-snapshot missed-transfer exposure</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Robust Miss Rate</div>
          <div class="metric-value">{robust_miss:.4f}</div>
          <div class="metric-detail">Average robust missed-transfer exposure</div>
        </article>
      </div>
      <div class="takeaway">
        <strong>Current takeaway:</strong> this slice is still a scaffold benchmark, but it now runs on a deterministic candidate set derived from observed departures instead of a tiny hand-written example. The next step is to replace this slice with a larger held-out evaluation window and publish stronger schedule-versus-robust accessibility-loss evidence.
      </div>
    </section>

    <section class="section">
      <h2>Tradeoff Summary</h2>
      <div class="metric-grid">
        <article class="metric-card">
          <div class="metric-label">Snapshot Regret</div>
          <div class="metric-value">{snapshot_regret:.2f} min</div>
          <div class="metric-detail">Average increase over schedule under realtime snapshot</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Robust Regret</div>
          <div class="metric-value">{robust_regret:.2f} min</div>
          <div class="metric-detail">Average increase over schedule under robust routing assumptions</div>
        </article>
      </div>
      <table>
        <thead>
          <tr>
            <th>OD</th>
            <th>Line</th>
            <th>Mode</th>
            <th>Scheduled</th>
            <th>Snapshot</th>
            <th>Robust</th>
            <th>Snapshot Miss</th>
            <th>Robust Miss</th>
            <th>Loss Flag</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
      <p class="takeaway">Artifacts: <code>results/benchmark/latest/candidates.csv</code>, <code>results/benchmark/latest/comparison.csv</code>, <code>results/benchmark/latest/summary.md</code>.</p>
    </section>
  </div>
</body>
</html>"""
    return html_doc


def render_dashboard(repo_root: Path, output_path: Path) -> Path:
    html_doc = build_benchmark_html(repo_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a static benchmark dashboard")
    parser.add_argument("--out", default="docs/benchmark_dashboard.html")
    args = parser.parse_args(argv)
    repo_root = _repo_root()
    written = render_dashboard(repo_root, (repo_root / args.out).resolve())
    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
