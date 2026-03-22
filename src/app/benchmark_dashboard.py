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


def _shell_html(title: str, eyebrow: str, heading: str, lede: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f4ede2;
      --paper: rgba(252, 248, 240, 0.94);
      --paper-strong: rgba(255, 252, 247, 0.98);
      --line: rgba(16, 36, 51, 0.11);
      --ink: #102433;
      --muted: #5c6b73;
      --accent: #0f4c5c;
      --accent-soft: rgba(15, 76, 92, 0.1);
      --accent-warm: #bf6d3a;
      --shadow: 0 24px 60px rgba(16, 36, 51, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Manrope", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(191, 109, 58, 0.12), transparent 24%),
        radial-gradient(circle at top right, rgba(15, 76, 92, 0.14), transparent 28%),
        linear-gradient(180deg, #fbf5ea 0%, #eef1eb 100%);
    }}
    .shell {{
      width: min(1240px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 72px;
    }}
    .hero,
    .section {{
      border-radius: 28px;
      border: 1px solid var(--line);
      background: var(--paper);
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 30px;
      background:
        radial-gradient(circle at top right, rgba(191, 109, 58, 0.12), transparent 26%),
        linear-gradient(135deg, rgba(255, 255, 255, 0.82), rgba(247, 240, 228, 0.9));
    }}
    .eyebrow {{
      margin: 0 0 12px;
      color: var(--accent);
      font-size: 0.76rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    h1, h2 {{
      margin: 0;
      font-family: "Fraunces", Georgia, serif;
      letter-spacing: -0.03em;
    }}
    h1 {{
      max-width: 12ch;
      font-size: clamp(2.7rem, 6vw, 5rem);
      line-height: 0.92;
    }}
    .lede {{
      max-width: 70ch;
      margin: 18px 0 0;
      color: var(--muted);
      line-height: 1.7;
      font-size: 1.02rem;
    }}
    .nav-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .nav-links a,
    .hero-tag {{
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(15, 76, 92, 0.12);
      background: rgba(255, 255, 255, 0.76);
      color: var(--ink);
      text-decoration: none;
      font-size: 0.84rem;
      font-weight: 700;
    }}
    .nav-links a.active {{
      background: rgba(15, 76, 92, 0.08);
      border-color: rgba(15, 76, 92, 0.3);
      color: var(--accent);
    }}
    .hero-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }}
    .section {{
      margin-top: 24px;
      padding: 24px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(255, 250, 244, 0.84));
    }}
    .section-head p,
    .takeaway,
    .empty-state p,
    .artifact-list li {{
      color: var(--muted);
      line-height: 1.65;
    }}
    .section-head {{
      margin-bottom: 18px;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .metric-card,
    .empty-state,
    .artifact-card {{
      border-radius: 20px;
      border: 1px solid rgba(15, 76, 92, 0.1);
      background: var(--paper-strong);
      padding: 16px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .metric-value {{
      margin-top: 8px;
      font-size: 1.5rem;
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
      border: 1px solid rgba(15, 76, 92, 0.12);
      background: rgba(15, 76, 92, 0.06);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 18px;
      font-size: 0.95rem;
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid rgba(16, 36, 51, 0.08);
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
      background: rgba(15, 76, 92, 0.08);
      padding: 2px 6px;
      border-radius: 8px;
    }}
    .artifact-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .artifact-list {{
      margin: 0;
      padding-left: 18px;
    }}
    @media (max-width: 980px) {{
      .metric-grid,
      .artifact-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      table {{
        display: block;
        overflow-x: auto;
      }}
    }}
    @media (max-width: 720px) {{
      .shell {{
        width: min(100vw - 20px, 100%);
        padding-top: 12px;
      }}
      .hero,
      .section {{
        padding: 18px;
        border-radius: 20px;
      }}
      .metric-grid,
      .artifact-grid {{
        grid-template-columns: 1fr;
      }}
      h1 {{
        max-width: none;
        font-size: 2.2rem;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <p class="eyebrow">{_escape(eyebrow)}</p>
      <h1>{_escape(heading)}</h1>
      <p class="lede">{lede}</p>
      <div class="nav-links">
        <a href="./index.html">Overview</a>
        <a href="./atlas.html">Atlas</a>
        <a class="active" href="./benchmark.html">Benchmark</a>
        <a href="./results.html">Research Review</a>
      </div>
      {body}
    </section>
  </div>
</body>
</html>"""


def _build_unavailable_html(repo_root: Path, output_path: Path, error: Exception) -> str:
    expected = [
        repo_root / "results" / "benchmark" / "latest" / "comparison.csv",
        repo_root / "results" / "benchmark" / "latest" / "summary.md",
        repo_root / "results" / "benchmark" / "latest" / "candidates.csv",
    ]
    cards = "".join(
        f"""
        <article class="artifact-card">
          <div class="metric-label">Expected artifact</div>
          <div class="metric-value">{_escape(path.name)}</div>
          <div class="metric-detail"><code>{_escape(path.relative_to(repo_root))}</code></div>
        </article>
        """
        for path in expected
    )
    body = f"""
      <div class="hero-tags">
        <span class="hero-tag">Fallback rendered</span>
        <span class="hero-tag">Awaiting benchmark artifacts</span>
      </div>
      <section class="section">
        <div class="section-head">
          <h2>Benchmark Artifacts Missing</h2>
          <p>The visual shell is ready, but the current worktree does not contain the committed benchmark result files needed to populate the comparison page.</p>
        </div>
        <div class="empty-state">
          <strong>Render error</strong>
          <p><code>{_escape(type(error).__name__)}</code>: {_escape(error)}</p>
        </div>
        <div class="artifact-grid">{cards}</div>
      </section>
    """
    return _shell_html(
        "Copenhagen Mobility Resilience Benchmark",
        "Benchmark dashboard",
        "Routing assumption benchmark, ready for data.",
        "This page is part of the unified public surface. Once benchmark artifacts are regenerated, it will show schedule-only, realtime-snapshot, and robust assumptions in the same visual language as the atlas and research review.",
        body,
    )


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

    body = f"""
      <div class="hero-tags">
        <span class="hero-tag">Deterministic candidate slice</span>
        <span class="hero-tag">Schedule vs snapshot vs robust</span>
        <span class="hero-tag">Decision-facing metrics</span>
      </div>
      <div class="metric-grid">
        <article class="metric-card">
          <div class="metric-label">Rows evaluated</div>
          <div class="metric-value">{total}</div>
          <div class="metric-detail">Current deterministic benchmark slice</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Scheduled access</div>
          <div class="metric-value">{scheduled_access}</div>
          <div class="metric-detail">Reachable within threshold on schedule</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Robust access</div>
          <div class="metric-value">{robust_access}</div>
          <div class="metric-detail">Reachable after reliability penalty is applied</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Access loss</div>
          <div class="metric-value">{access_loss}</div>
          <div class="metric-detail">Cases pushed outside the threshold by uncertainty</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Snapshot miss rate</div>
          <div class="metric-value">{snapshot_miss:.4f}</div>
          <div class="metric-detail">Average missed-transfer exposure under snapshot assumptions</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">Robust miss rate</div>
          <div class="metric-value">{robust_miss:.4f}</div>
          <div class="metric-detail">Average missed-transfer exposure under robust assumptions</div>
        </article>
      </div>
      <section class="section">
        <div class="section-head">
          <h2>Trade-off summary</h2>
          <p>This slice is still scaffold-scale, but it already shows how a single candidate set can support multiple decision assumptions in one page.</p>
        </div>
        <div class="metric-grid">
          <article class="metric-card">
            <div class="metric-label">Snapshot regret</div>
            <div class="metric-value">{snapshot_regret:.2f} min</div>
            <div class="metric-detail">Average increase over schedule under realtime snapshot</div>
          </article>
          <article class="metric-card">
            <div class="metric-label">Robust regret</div>
            <div class="metric-value">{robust_regret:.2f} min</div>
            <div class="metric-detail">Average increase over schedule under robust routing assumptions</div>
          </article>
        </div>
        <div class="takeaway"><strong>Current takeaway:</strong> the benchmark is already useful as a communication layer. The next step is scale: a larger held-out evaluation window, more routes, and sharper schedule-versus-robust accessibility-loss evidence.</div>
        <table>
          <thead>
            <tr>
              <th>OD</th>
              <th>Line</th>
              <th>Mode</th>
              <th>Scheduled</th>
              <th>Snapshot</th>
              <th>Robust</th>
              <th>Snapshot miss</th>
              <th>Robust miss</th>
              <th>Loss flag</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
        <p class="takeaway">Artifacts: <code>results/benchmark/latest/candidates.csv</code>, <code>results/benchmark/latest/comparison.csv</code>, <code>results/benchmark/latest/summary.md</code>.</p>
      </section>
    """
    return _shell_html(
        "Copenhagen Mobility Resilience Benchmark",
        "Benchmark dashboard",
        "Reliability-aware benchmark for routing assumptions.",
        "This page compares schedule-only, realtime-snapshot, and robust assumptions on a deterministic candidate slice. It is meant to sit beside the atlas and research review as the operational comparison layer of the public site.",
        body,
    )


def render_dashboard(repo_root: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        html_doc = build_benchmark_html(repo_root, output_path)
    except Exception as exc:  # pragma: no cover
        html_doc = _build_unavailable_html(repo_root, output_path, exc)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a static benchmark dashboard")
    parser.add_argument("--out", default="web/accessibility/benchmark.html")
    args = parser.parse_args(argv)
    repo_root = _repo_root()
    written = render_dashboard(repo_root, (repo_root / args.out).resolve())
    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
