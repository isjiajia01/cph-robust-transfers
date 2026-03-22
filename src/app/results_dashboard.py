from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from pathlib import Path

from src.common.io import ensure_parent, utc_now_iso


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel_href(target: Path, out_dir: Path) -> str:
    return os.path.relpath(target, out_dir).replace(os.sep, "/")


def _extract_or_raise(pattern: str, text: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"Pattern not found: {pattern}")
    return match


def _num(value: str | int | float) -> float:
    return float(value)


def _escape(value: object) -> str:
    return html.escape(str(value))


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _fmt_float(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def _fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


def _fmt_ratio_pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:.{decimals}f}%"


def _fmt_seconds(value: float) -> str:
    return f"{int(round(value))}s"


def _fmt_minutes(value: float) -> str:
    return f"{value:.1f} min"


def _fmt_compact(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}"


def _band_for_p95(p95_delay_sec: float) -> str:
    if p95_delay_sec <= 60:
        return "Leading"
    if p95_delay_sec <= 120:
        return "Stable"
    if p95_delay_sec <= 240:
        return "Watchlist"
    if p95_delay_sec <= 360:
        return "At Risk"
    return "Critical"


def _band_tone(band: str) -> str:
    return {
        "Leading": "positive",
        "Stable": "positive",
        "Watchlist": "neutral",
        "At Risk": "warning",
        "Critical": "critical",
    }[band]


def _parse_week1_summary(path: Path) -> dict:
    text = _read_text(path)
    stops = int(_extract_or_raise(r"Stops \(nodes\):\s*([0-9]+)", text).group(1))
    edges = int(_extract_or_raise(r"Directed edges:\s*([0-9]+)", text).group(1))
    largest = _extract_or_raise(
        r"Largest connected component size:\s*([0-9]+)\s*\(([0-9.]+)%\)",
        text,
    )
    hubs = []
    for line in text.splitlines():
        hub_match = re.match(
            r"- (.+?) \(`([^`]+)`\): degree=([0-9]+), in=([0-9]+), out=([0-9]+)",
            line,
        )
        if hub_match:
            hubs.append(
                {
                    "name": hub_match.group(1),
                    "stop_id": hub_match.group(2),
                    "degree": int(hub_match.group(3)),
                    "in_degree": int(hub_match.group(4)),
                    "out_degree": int(hub_match.group(5)),
                }
            )
    return {
        "stops": stops,
        "edges": edges,
        "largest_component_size": int(largest.group(1)),
        "largest_component_ratio_pct": float(largest.group(2)),
        "top_hubs": hubs,
    }


def _parse_week3_conclusions(path: Path) -> dict:
    text = _read_text(path)
    window_days = int(_extract_or_raise(r"Window: last `([0-9]+)` day", text).group(1))
    observations = int(
        _extract_or_raise(r"Effective observations across ranked lines: `([0-9]+)`", text).group(1)
    )
    timezone = _extract_or_raise(r"Timezone: `([^`]+)`", text).group(1)
    return {
        "window_days": window_days,
        "observations": observations,
        "timezone": timezone,
    }


def _parse_robustness_summary(path: Path) -> dict:
    text = _read_text(path)
    data_date = _extract_or_raise(r"Data date: `([^`]+)`", text).group(1)
    version = _extract_or_raise(r"GTFS feed version: `([^`]+)`", text).group(1)
    nodes_edges = _extract_or_raise(r"Nodes / edges: `([0-9]+)` / `([0-9]+)`", text)
    checkpoints = []
    for match in re.finditer(
        r"At `([0-9]+)%` removal: random LCC avg=`([0-9.]+)`, targeted LCC avg=`([0-9.]+)`",
        text,
    ):
        checkpoints.append(
            {
                "removal_pct": int(match.group(1)),
                "random_lcc": float(match.group(2)),
                "targeted_lcc": float(match.group(3)),
            }
        )
    return {
        "data_date": data_date,
        "gtfs_feed_version": version,
        "nodes": int(nodes_edges.group(1)),
        "edges": int(nodes_edges.group(2)),
        "checkpoints": checkpoints,
    }


def _load_stop_reference(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    rows = _load_csv(path)
    by_id = {row["stop_id"]: row for row in rows if row.get("stop_id")}
    return by_id, rows


def _find_stop_record(
    stop_id: str,
    stop_name: str,
    by_id: dict[str, dict[str, str]],
    rows: list[dict[str, str]],
) -> dict[str, str] | None:
    if stop_id and stop_id in by_id:
        return by_id[stop_id]

    target = stop_name.strip().lower()
    if not target:
        return None

    for row in rows:
        if row.get("stop_name", "").strip().lower() == target:
            return row

    for row in rows:
        if target in row.get("stop_name", "").strip().lower():
            return row

    return None


def _prepare_reliability_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    prepared = []
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _num(row["p95_delay_sec"]),
            _num(row["avg_delay_sec"]),
            -_num(row["n"]),
            row["line"],
        ),
    )
    for index, row in enumerate(sorted_rows, start=1):
        p50 = int(_num(row["p50_delay_sec"]))
        p90 = int(_num(row["p90_delay_sec"]))
        p95 = int(_num(row["p95_delay_sec"]))
        avg = round(_num(row["avg_delay_sec"]), 2)
        sample_size = int(_num(row["n"]))
        band = _band_for_p95(p95)
        prepared.append(
            {
                "line": row["line"],
                "rank": index,
                "p50_delay_sec": p50,
                "p90_delay_sec": p90,
                "p95_delay_sec": p95,
                "avg_delay_sec": avg,
                "n": sample_size,
                "band": band,
                "tone": _band_tone(band),
            }
        )
    return prepared


def _prepare_hour_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    prepared = []
    for row in sorted(rows, key=lambda item: int(item["hour_cph"])):
        prepared.append(
            {
                "hour_cph": int(row["hour_cph"]),
                "dow_cph": int(row["dow_cph"]),
                "p50_delay_sec": int(_num(row["p50_delay_sec"])),
                "p90_delay_sec": int(_num(row["p90_delay_sec"])),
                "p95_delay_sec": int(_num(row["p95_delay_sec"])),
                "n": int(_num(row["n"])),
            }
        )
    return prepared


def _prepare_router_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    prepared = []
    for row in rows:
        prepared.append(
            {
                "od_id": row["od_id"],
                "depart_ts_cph": row["depart_ts_cph"],
                "path_id": row["path_id"],
                "travel_time_min": round(_num(row["travel_time_min"]), 2),
                "transfers": int(_num(row["transfers"])),
                "miss_prob": round(_num(row["miss_prob"]), 4),
                "cvar95_min": round(_num(row["cvar95_min"]), 2),
                "evidence_level": row["evidence_level"],
                "sample_size_effective": int(_num(row["sample_size_effective"])),
                "confidence_tag": row["confidence_tag"],
                "ci95_width_sec": int(_num(row["ci95_width_sec"])),
                "hour_cph": int(_num(row["hour_cph"])),
            }
        )
    return prepared


def _prepare_risk_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    prepared = []
    for row in rows:
        prepared.append(
            {
                "line": row["line"],
                "mode": row["mode"],
                "p50_delay_sec": int(_num(row["p50_delay_sec"])),
                "p90_delay_sec": int(_num(row["p90_delay_sec"])),
                "p95_delay_sec": int(_num(row["p95_delay_sec"])),
                "p95_ci_low": int(_num(row["p95_ci_low"])),
                "p95_ci_high": int(_num(row["p95_ci_high"])),
                "sample_size_effective": int(_num(row["sample_size_effective"])),
                "confidence_tag": row["confidence_tag"],
                "evidence_level": row["evidence_level"],
                "source_level": row["source_level"],
                "ci95_width_sec": int(_num(row["ci95_width_sec"])),
                "risk_model_version": row["risk_model_version"],
            }
        )
    return prepared


def _enrich_map_points(
    week1: dict,
    vulnerable_rows: list[dict[str, str]],
    stop_by_id: dict[str, dict[str, str]],
    stop_rows: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    hubs = []
    for hub in week1["top_hubs"][:8]:
        stop = _find_stop_record(hub["stop_id"], hub["name"], stop_by_id, stop_rows)
        if stop is None:
            continue
        hubs.append(
            {
                "id": f"hub-{hub['stop_id']}",
                "layer": "hub",
                "label": stop.get("stop_name") or hub["name"],
                "stop_id": hub["stop_id"],
                "lat": float(stop["stop_lat"]),
                "lon": float(stop["stop_lon"]),
                "primary_metric_label": "Degree",
                "primary_metric_value": hub["degree"],
                "secondary_metric_label": "In/Out",
                "secondary_metric_value": f"{hub['in_degree']} / {hub['out_degree']}",
                "narrative": "Most connected static transfer hubs by degree.",
                "tone": "hub",
            }
        )

    vulnerable = []
    for row in vulnerable_rows:
        stop = _find_stop_record(row["stop_id"], "", stop_by_id, stop_rows)
        if stop is None:
            continue
        vulnerable.append(
            {
                "id": f"vuln-{row['stop_id']}",
                "layer": "vulnerable",
                "label": stop.get("stop_name") or row["stop_id"],
                "stop_id": row["stop_id"],
                "lat": float(stop["stop_lat"]),
                "lon": float(stop["stop_lon"]),
                "primary_metric_label": "Betweenness",
                "primary_metric_value": round(_num(row["betweenness_score"]), 2),
                "secondary_metric_label": "Impact delta LCC",
                "secondary_metric_value": row["impact_delta_lcc"],
                "narrative": row["planning_implication"],
                "tone": "vulnerable",
            }
        )

    return hubs, vulnerable, hubs + vulnerable


def _render_metric_card(label: str, value: str, detail: str, tone: str = "neutral") -> str:
    return (
        f'<article class="metric-card metric-card--{_escape(tone)}">'
        f'<div class="metric-label">{_escape(label)}</div>'
        f'<div class="metric-value">{_escape(value)}</div>'
        f'<div class="metric-detail">{_escape(detail)}</div>'
        "</article>"
    )


def _render_table(headers: list[str], rows: list[list[str]], table_id: str | None = None) -> str:
    thead = "".join(f"<th>{_escape(header)}</th>" for header in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{_escape(cell)}</td>" for cell in row) + "</tr>")
    table_attr = f' id="{_escape(table_id)}"' if table_id else ""
    return f"<table{table_attr}><thead><tr>{thead}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _render_hour_chart(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""

    width = 680
    height = 280
    left_pad = 56
    right_pad = 18
    top_pad = 24
    bottom_pad = 40
    chart_width = width - left_pad - right_pad
    chart_height = height - top_pad - bottom_pad
    max_value = max(row["p95_delay_sec"] for row in rows) or 1
    step_x = chart_width / max(len(rows) - 1, 1)
    points = []
    for index, row in enumerate(rows):
        x = left_pad + index * step_x
        y = top_pad + chart_height - chart_height * (row["p95_delay_sec"] / max_value)
        points.append((x, y, row))

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Delay tail by hour">']
    for tick in range(5):
        ratio = tick / 4
        y = top_pad + chart_height - chart_height * ratio
        value = max_value * ratio
        parts.append(
            f'<line x1="{left_pad}" y1="{y}" x2="{width - right_pad}" y2="{y}" class="grid-line"></line>'
            f'<text x="{left_pad - 8}" y="{y + 4}" text-anchor="end" class="axis-label">{_fmt_seconds(value)}</text>'
        )
    path = " ".join(f"{x},{y}" for x, y, _row in points)
    parts.append(f'<polyline fill="none" stroke="#0f766e" stroke-width="4" points="{path}"></polyline>')
    for x, y, row in points:
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="5.5" fill="#0f766e"></circle>'
            f'<text x="{x}" y="{height - 14}" text-anchor="middle" class="axis-label">{row["hour_cph"]}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _render_checkpoint_chart(checkpoints: list[dict[str, object]]) -> str:
    if not checkpoints:
        return ""

    width = 680
    height = 280
    left_pad = 62
    right_pad = 16
    top_pad = 20
    bottom_pad = 46
    chart_width = width - left_pad - right_pad
    chart_height = height - top_pad - bottom_pad
    group_width = chart_width / max(len(checkpoints), 1)
    bar_width = min(34, group_width / 3)

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Random versus targeted failure">']
    for tick in range(6):
        ratio = tick / 5
        y = top_pad + chart_height - chart_height * ratio
        parts.append(
            f'<line x1="{left_pad}" y1="{y}" x2="{width - right_pad}" y2="{y}" class="grid-line"></line>'
            f'<text x="{left_pad - 8}" y="{y + 4}" text-anchor="end" class="axis-label">{ratio:.1f}</text>'
        )
    for index, row in enumerate(checkpoints):
        x0 = left_pad + index * group_width + (group_width - (2 * bar_width + 10)) / 2
        random_h = chart_height * float(row["random_lcc"])
        targeted_h = chart_height * float(row["targeted_lcc"])
        parts.append(
            f'<rect x="{x0}" y="{top_pad + chart_height - random_h}" width="{bar_width}" height="{random_h}" rx="10" fill="#0f766e"></rect>'
            f'<rect x="{x0 + bar_width + 10}" y="{top_pad + chart_height - targeted_h}" width="{bar_width}" height="{targeted_h}" rx="10" fill="#d97706"></rect>'
            f'<text x="{x0 + bar_width}" y="{height - 14}" text-anchor="middle" class="axis-label">{row["removal_pct"]}%</text>'
        )
    parts.append(
        f'<text x="{left_pad}" y="{height - 2}" class="legend-item"><tspan fill="#0f766e">random</tspan> vs <tspan fill="#d97706">targeted</tspan></text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _render_figure_card(title: str, caption: str, href: str) -> str:
    return (
        '<article class="figure-card">'
        f'<img src="{_escape(href)}" alt="{_escape(title)}" loading="lazy">'
        f"<h4>{_escape(title)}</h4>"
        f"<p>{_escape(caption)}</p>"
        "</article>"
    )


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=True).replace("</", "<\\/")


def _build_unavailable_dashboard_html(repo_root: Path, output_path: Path, error: Exception) -> str:
    output_rel = _rel_href(output_path, repo_root)
    expected = [
        repo_root / "docs" / "week1_summary.md",
        repo_root / "docs" / "week3_conclusions.md",
        repo_root / "results" / "robustness" / "summary.md",
        repo_root / "data" / "analysis" / "week3_line_reliability_rank.csv",
        repo_root / "data" / "analysis" / "week3_hour_dow_quantiles.csv",
        repo_root / "data" / "analysis" / "router_pareto_table.csv",
        repo_root / "data" / "analysis" / "risk_model_mode_level.csv",
    ]
    missing_items = "".join(
        f'<div class="source-item"><strong>{_escape(path.name)}</strong><code>{_escape(path.relative_to(repo_root))}</code></div>'
        for path in expected
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Copenhagen Mobility Resilience Research Review</title>
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
    .section {{
      margin-top: 24px;
      padding: 24px;
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
    p, li {{
      color: var(--muted);
      line-height: 1.7;
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
    .hero-tag {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(15, 76, 92, 0.12);
      background: rgba(255, 255, 255, 0.76);
      color: var(--ink);
      font-size: 0.84rem;
      font-weight: 700;
    }}
    .empty-state,
    .source-item {{
      border-radius: 20px;
      border: 1px solid rgba(15, 76, 92, 0.1);
      background: var(--paper-strong);
      padding: 16px;
    }}
    .source-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .source-item strong {{
      display: block;
      margin-bottom: 6px;
      color: var(--ink);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    code {{
      background: rgba(15, 76, 92, 0.08);
      padding: 2px 6px;
      border-radius: 8px;
      word-break: break-word;
    }}
    @media (max-width: 720px) {{
      .shell {{ width: min(100vw - 20px, 100%); padding-top: 12px; }}
      .hero, .section {{ padding: 18px; border-radius: 20px; }}
      .source-grid {{ grid-template-columns: 1fr; }}
      h1 {{ max-width: none; font-size: 2.2rem; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">Research review</p>
      <h1>Research dashboard shell is ready for regenerated artifacts.</h1>
      <p>This page shares the same public-facing language as the overview, atlas, and benchmark layers. The current worktree is missing one or more committed result files, so the generator emitted an auditable placeholder instead of failing silently.</p>
      <div class="nav-links">
        <a href="./index.html">Overview</a>
        <a href="./atlas.html">Atlas</a>
        <a href="./benchmark.html">Benchmark</a>
        <a class="active" href="./results.html">Research Review</a>
      </div>
      <div class="hero-tags">
        <span class="hero-tag">Fallback rendered</span>
        <span class="hero-tag">Awaiting regenerated results</span>
      </div>
    </section>
    <section class="section">
      <h2>Render status</h2>
      <div class="empty-state">
        <p><strong>{_escape(type(error).__name__)}</strong>: {_escape(error)}</p>
        <p>Target output: <code>{_escape(output_rel)}</code></p>
      </div>
      <div class="source-grid">{missing_items}</div>
    </section>
  </main>
</body>
</html>"""


def build_dashboard_html(repo_root: Path, output_path: Path) -> str:
    docs_dir = repo_root / "docs"
    out_dir = output_path.parent

    week1 = _parse_week1_summary(docs_dir / "week1_summary.md")
    week3 = _parse_week3_conclusions(docs_dir / "week3_conclusions.md")
    robustness = _parse_robustness_summary(repo_root / "results" / "robustness" / "summary.md")
    week3_summary = _load_json(
        repo_root / "data" / "analysis" / "reports" / "week3" / "dt=2026-03-02" / "summary.json"
    )

    reliability_rows = _prepare_reliability_rows(
        _load_csv(repo_root / "data" / "analysis" / "week3_line_reliability_rank.csv")
    )
    hour_rows = _prepare_hour_rows(_load_csv(repo_root / "data" / "analysis" / "week3_hour_dow_quantiles.csv"))
    router_rows = _prepare_router_rows(_load_csv(repo_root / "data" / "analysis" / "router_pareto_table.csv"))
    risk_rows = _prepare_risk_rows(_load_csv(repo_root / "data" / "analysis" / "risk_model_mode_level.csv"))
    vulnerable_rows = _load_csv(repo_root / "results" / "robustness" / "top10_vulnerable_nodes.csv")

    stop_by_id, stop_rows = _load_stop_reference(repo_root / "data" / "gtfs" / "parsed" / "20260302" / "stops.csv")
    top_hub_points, vulnerable_points, map_points = _enrich_map_points(
        week1,
        vulnerable_rows,
        stop_by_id,
        stop_rows,
    )

    best_line = reliability_rows[0]
    worst_line = max(reliability_rows, key=lambda row: row["p95_delay_sec"])
    network_median_row = reliability_rows[len(reliability_rows) // 2]
    critical_lines = sum(1 for row in reliability_rows if row["band"] == "Critical")
    leading_lines = sum(1 for row in reliability_rows if row["band"] == "Leading")
    watchlist_lines = sum(1 for row in reliability_rows if row["band"] in {"Watchlist", "At Risk", "Critical"})
    attack_gap_ratio = (
        robustness["checkpoints"][1]["random_lcc"] / robustness["checkpoints"][1]["targeted_lcc"]
        if robustness["checkpoints"][1]["targeted_lcc"]
        else 0.0
    )

    metric_cards = "".join(
        [
            _render_metric_card(
                "Static network size",
                _fmt_int(week1["stops"]),
                f"{_fmt_int(week1['edges'])} directed edges in the GTFS graph",
                "neutral",
            ),
            _render_metric_card(
                "Lines tracked",
                _fmt_int(len(reliability_rows)),
                f"{leading_lines} in the leadership band",
                "positive",
            ),
            _render_metric_card(
                "Worst line tail",
                _fmt_seconds(worst_line["p95_delay_sec"]),
                f"{worst_line['line']} is the current upper-tail outlier",
                "critical",
            ),
            _render_metric_card(
                "Median P95",
                _fmt_seconds(network_median_row["p95_delay_sec"]),
                "Portfolio midpoint across ranked lines",
                "neutral",
            ),
            _render_metric_card(
                "Watchlist exposure",
                _fmt_int(watchlist_lines),
                "Lines above a 240s P95 or approaching it",
                "warning",
            ),
            _render_metric_card(
                "Coverage caveat",
                _fmt_ratio_pct(week3_summary["sampling_24h"]["coverage_ratio"], 1),
                "24h Task A snapshot, use as operational evidence not service truth",
                "neutral",
            ),
            _render_metric_card(
                "Targeted attack penalty",
                f"{attack_gap_ratio:.1f}x",
                "Random vs targeted LCC ratio at 15% removal",
                "warning",
            ),
        ]
    )

    executive_cards = "".join(
        [
            (
                '<article class="insight-card">'
                "<h3>Leadership story</h3>"
                f"<p><strong>{_escape(best_line['line'])}</strong> leads the portfolio with a { _escape(_fmt_seconds(best_line['p95_delay_sec'])) } P95. "
                "The company-facing message is that the network already has visibly dependable services worth using as operational benchmarks.</p>"
                "</article>"
            ),
            (
                '<article class="insight-card">'
                "<h3>Immediate risk</h3>"
                f"<p><strong>{_escape(worst_line['line'])}</strong> reaches a { _escape(_fmt_seconds(worst_line['p95_delay_sec'])) } P95 tail. "
                "That is where delay communication, schedule padding, and intervention planning should start.</p>"
                "</article>"
            ),
            (
                '<article class="insight-card">'
                "<h3>Structural fragility</h3>"
                f"<p>At 15% node removal, targeted failures shrink the largest connected component from { _escape(_fmt_float(robustness['checkpoints'][1]['random_lcc'], 3)) } to "
                f"{ _escape(_fmt_float(robustness['checkpoints'][1]['targeted_lcc'], 3)) }. The network is bridge-sensitive, not evenly resilient.</p>"
                "</article>"
            ),
        ]
    )

    map_summary_table = _render_table(
        ["stop", "type", "metric", "value"],
        [
            [point["label"], point["layer"], point["primary_metric_label"], _fmt_compact(_num(point["primary_metric_value"]))]
            for point in map_points[:8]
        ],
    )

    risk_table = _render_table(
        ["line", "mode", "p95", "CI low", "CI high", "evidence", "source"],
        [
            [
                row["line"],
                row["mode"],
                _fmt_seconds(row["p95_delay_sec"]),
                _fmt_seconds(row["p95_ci_low"]),
                _fmt_seconds(row["p95_ci_high"]),
                row["evidence_level"],
                row["source_level"],
            ]
            for row in risk_rows
        ],
    )

    router_table = _render_table(
        ["od", "path", "travel time", "transfers", "miss prob", "CVaR95", "confidence"],
        [
            [
                row["od_id"],
                row["path_id"],
                _fmt_minutes(row["travel_time_min"]),
                str(row["transfers"]),
                f"{row['miss_prob']:.3f}",
                _fmt_minutes(row["cvar95_min"]),
                row["confidence_tag"],
            ]
            for row in router_rows
        ],
    )

    figures = "".join(
        [
            _render_figure_card(
                "Week 1 connectivity profile",
                "Static connectivity footprint of the national GTFS graph used as the baseline.",
                _rel_href(docs_dir / "figures" / "week1_component_sizes.png", out_dir),
            ),
            _render_figure_card(
                "Week 2 targeted vs random",
                "Published robustness curve comparing random failures to betweenness-targeted attacks.",
                _rel_href(repo_root / "results" / "robustness" / "random_vs_targeted_curve.png", out_dir),
            ),
            _render_figure_card(
                "Week 3 line reliability",
                "Committed seven-day line ranking by P95 delay.",
                _rel_href(docs_dir / "figures" / "week3_line_reliability_rank.png", out_dir),
            ),
            _render_figure_card(
                "Week 3 daypart pattern",
                "Delay tail by Copenhagen local hour from the committed BQ-derived analysis.",
                _rel_href(docs_dir / "figures" / "week3_p95_by_hour_cph.png", out_dir),
            ),
        ]
    )

    source_items = [
        ("week1_summary", _rel_href(docs_dir / "week1_summary.md", out_dir)),
        ("robustness_summary", _rel_href(repo_root / "results" / "robustness" / "summary.md", out_dir)),
        ("robustness_nodes", _rel_href(repo_root / "results" / "robustness" / "top10_vulnerable_nodes.csv", out_dir)),
        (
            "week3_summary_json",
            _rel_href(
                repo_root / "data" / "analysis" / "reports" / "week3" / "dt=2026-03-02" / "summary.json",
                out_dir,
            ),
        ),
        (
            "week3_reliability",
            _rel_href(repo_root / "data" / "analysis" / "week3_line_reliability_rank.csv", out_dir),
        ),
        (
            "hour_quantiles",
            _rel_href(repo_root / "data" / "analysis" / "week3_hour_dow_quantiles.csv", out_dir),
        ),
        (
            "router_table",
            _rel_href(repo_root / "data" / "analysis" / "router_pareto_table.csv", out_dir),
        ),
        (
            "risk_model",
            _rel_href(repo_root / "data" / "analysis" / "risk_model_mode_level.csv", out_dir),
        ),
    ]

    dashboard_data = {
        "portfolio": {
            "reliability": reliability_rows,
            "network_median_p95": network_median_row["p95_delay_sec"],
            "worst_p95": worst_line["p95_delay_sec"],
            "best_p95": best_line["p95_delay_sec"],
            "default_selected_line": worst_line["line"],
            "band_order": ["Leading", "Stable", "Watchlist", "At Risk", "Critical"],
        },
        "map": {
            "default_selected_point_id": vulnerable_points[0]["id"] if vulnerable_points else (top_hub_points[0]["id"] if top_hub_points else ""),
            "points": map_points,
        },
    }

    source_grid = "".join(
        f'<div class="source-item"><strong>{_escape(name)}</strong><code>{_escape(path)}</code></div>'
        for name, path in source_items
    )

    hour_chart = _render_hour_chart(hour_rows)
    checkpoint_chart = _render_checkpoint_chart(robustness["checkpoints"])

    template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Copenhagen Mobility Resilience Research Review</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f4ede2;
      --ink: #102433;
      --muted: #5c6b73;
      --panel: rgba(252, 248, 240, 0.94);
      --panel-strong: rgba(255, 252, 247, 0.98);
      --line: rgba(16, 36, 51, 0.11);
      --teal: #0f4c5c;
      --blue: #2d7b8a;
      --amber: #bf6d3a;
      --red: #b91c1c;
      --cream: #fbf5ea;
      --shadow: 0 24px 60px rgba(16, 36, 51, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Manrope", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(191, 109, 58, 0.12), transparent 24%),
        radial-gradient(circle at top right, rgba(15, 76, 92, 0.14), transparent 28%),
        linear-gradient(180deg, #fbf5ea 0%, #eef1eb 100%);
    }
    h1, h2 {
      font-family: "Fraunces", Georgia, serif;
      letter-spacing: -0.03em;
    }
    a { color: inherit; }
    .shell {
      width: min(1320px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 72px;
    }
    .hero,
    .section {
      position: relative;
      overflow: hidden;
      border-radius: 30px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      animation: rise 720ms ease;
    }
    .hero {
      padding: 34px;
      background:
        radial-gradient(circle at top right, rgba(191, 109, 58, 0.12), transparent 28%),
        linear-gradient(135deg, rgba(255,255,255,0.96), rgba(250,244,235,0.86));
    }
    .hero-grid {
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 24px;
      align-items: end;
    }
    .eyebrow {
      margin: 0 0 12px;
      color: var(--teal);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    h1 {
      margin: 0;
      max-width: 12ch;
      font-size: clamp(2.9rem, 6vw, 5.4rem);
      line-height: 0.92;
    }
    .hero-copy {
      max-width: 68ch;
      margin: 18px 0 0;
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.7;
    }
    .nav-links,
    .hero-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .nav-links {
      margin-top: 18px;
    }
    .hero-tags {
      margin-top: 16px;
    }
    .nav-links a,
    .hero-tag {
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
    }
    .nav-links a.active {
      background: rgba(15, 76, 92, 0.08);
      border-color: rgba(15, 76, 92, 0.3);
      color: var(--teal);
    }
    .hero-panel {
      padding: 22px;
      border-radius: 22px;
      border: 1px solid rgba(16, 34, 44, 0.08);
      background: rgba(15, 76, 92, 0.05);
    }
    .hero-panel h3 {
      margin: 0 0 10px;
      font-size: 1rem;
    }
    .hero-panel p {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }
    .hero-signals {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 22px;
    }
    .signal-card {
      padding: 18px;
      border-radius: 22px;
      border: 1px solid rgba(16, 34, 44, 0.08);
      background: rgba(255,255,255,0.88);
    }
    .signal-card h3 {
      margin: 0 0 8px;
      font-size: 1rem;
    }
    .signal-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
      font-size: 0.95rem;
    }
    .section {
      margin-top: 24px;
      padding: 28px;
      background: linear-gradient(180deg, rgba(255,255,255,0.88), rgba(255,250,244,0.84));
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 16px;
      margin-bottom: 18px;
    }
    .section-head h2 {
      margin: 0;
      font-size: clamp(2rem, 4vw, 2.9rem);
    }
    .section-head p {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
      max-width: 70ch;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 14px;
    }
    .metric-card {
      padding: 18px;
      border-radius: 22px;
      border: 1px solid rgba(16, 34, 44, 0.08);
      background: rgba(255,255,255,0.9);
      transition: transform 180ms ease, border-color 180ms ease;
    }
    .metric-card:hover {
      transform: translateY(-2px);
      border-color: rgba(15, 118, 110, 0.20);
    }
    .metric-card--positive { background: linear-gradient(180deg, rgba(232, 243, 243, 0.92), rgba(255,255,255,0.92)); }
    .metric-card--warning { background: linear-gradient(180deg, rgba(251, 237, 231, 0.92), rgba(255,255,255,0.92)); }
    .metric-card--critical { background: linear-gradient(180deg, rgba(254, 242, 242, 0.92), rgba(255,255,255,0.92)); }
    .metric-label {
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.10em;
    }
    .metric-value {
      margin-top: 10px;
      font-size: clamp(1.5rem, 2.3vw, 2.2rem);
      font-weight: 700;
      line-height: 1;
    }
    .metric-detail {
      margin-top: 10px;
      color: var(--muted);
      line-height: 1.55;
      font-size: 0.93rem;
    }
    .insight-grid,
    .portfolio-grid,
    .geo-grid,
    .decision-grid,
    .figure-grid,
    .source-grid {
      display: grid;
      gap: 18px;
    }
    .insight-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 18px;
    }
    .insight-card,
    .panel {
      padding: 20px;
      border-radius: 24px;
      border: 1px solid rgba(16, 34, 44, 0.08);
      background: var(--panel-strong);
    }
    .insight-card h3,
    .panel h3,
    .panel h4 {
      margin: 0 0 10px;
    }
    .insight-card p,
    .panel-copy,
    .small-note {
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
    }
    .control-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin: 18px 0;
    }
    .control {
      min-width: 180px;
      flex: 1 1 180px;
    }
    .control label {
      display: block;
      margin-bottom: 7px;
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .control input,
    .control select {
      width: 100%;
      border: 1px solid rgba(16, 34, 44, 0.14);
      border-radius: 14px;
      background: #fff;
      color: var(--ink);
      padding: 12px 14px;
      font: inherit;
    }
    .portfolio-grid {
      grid-template-columns: 1.05fr 0.95fr;
      align-items: start;
    }
    .geo-grid {
      grid-template-columns: 1.2fr 0.8fr;
      align-items: start;
    }
    .decision-grid {
      grid-template-columns: 0.95fr 1.05fr;
      align-items: start;
    }
    .figure-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin-top: 18px;
    }
    .source-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 18px;
    }
    .data-cards {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .data-card {
      padding: 14px;
      border-radius: 18px;
      background: rgba(16, 34, 44, 0.04);
      border: 1px solid rgba(16, 34, 44, 0.08);
    }
    .data-card .label {
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.10em;
    }
    .data-card .value {
      margin-top: 8px;
      font-size: 1.4rem;
      font-weight: 700;
    }
    .data-card .meta {
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.9rem;
    }
    .tone-pill,
    .legend-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 11px;
      border-radius: 999px;
      font-size: 0.84rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .tone-pill::before,
    .legend-pill::before {
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: currentColor;
    }
    .tone-leading { color: #0f766e; background: rgba(15, 118, 110, 0.10); }
    .tone-stable { color: #0e7490; background: rgba(14, 116, 144, 0.10); }
    .tone-watchlist { color: #b45309; background: rgba(180, 83, 9, 0.11); }
    .tone-at-risk { color: #c2410c; background: rgba(194, 65, 12, 0.11); }
    .tone-critical { color: #b91c1c; background: rgba(185, 28, 28, 0.10); }
    .legend-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }
    .legend-vulnerable { color: #b91c1c; background: rgba(185, 28, 28, 0.10); }
    .legend-hub { color: #164e63; background: rgba(22, 78, 99, 0.10); }
    .ranking-chart,
    .line-bars {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 132px 1fr auto;
      gap: 10px;
      align-items: center;
    }
    .bar-track {
      position: relative;
      height: 14px;
      border-radius: 999px;
      background: rgba(16, 34, 44, 0.08);
      overflow: hidden;
    }
    .bar-fill {
      height: 100%;
      border-radius: inherit;
    }
    .bar-fill--teal { background: linear-gradient(90deg, #0f766e, #14b8a6); }
    .bar-fill--amber { background: linear-gradient(90deg, #d97706, #f59e0b); }
    .bar-fill--red { background: linear-gradient(90deg, #b91c1c, #ef4444); }
    .selected-banner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .selected-banner h3 {
      margin: 0;
      font-size: 1.45rem;
    }
    .selected-meta {
      color: var(--muted);
      font-size: 0.95rem;
    }
    .line-table-wrap {
      overflow-x: auto;
      margin-top: 18px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      padding: 12px 0;
      border-bottom: 1px solid rgba(16, 34, 44, 0.08);
      text-align: left;
      vertical-align: top;
      font-size: 0.95rem;
    }
    th {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.78rem;
    }
    .line-row {
      cursor: pointer;
      transition: background 160ms ease;
    }
    .line-row:hover {
      background: rgba(16, 34, 44, 0.04);
    }
    .line-row.is-selected {
      background: rgba(15, 118, 110, 0.08);
    }
    .line-button {
      border: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      padding: 0;
      cursor: pointer;
    }
    .table-note {
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.92rem;
    }
    .geo-map {
      min-height: 520px;
      border-radius: 24px;
      background:
        radial-gradient(circle at center, rgba(15, 118, 110, 0.08), transparent 45%),
        linear-gradient(180deg, rgba(22, 78, 99, 0.04), rgba(255,255,255,0.88));
      border: 1px solid rgba(16, 34, 44, 0.08);
      padding: 12px;
    }
    .geo-map svg {
      width: 100%;
      height: auto;
      display: block;
    }
    .map-tooltip {
      padding: 16px;
      border-radius: 18px;
      background: rgba(16, 34, 44, 0.04);
      border: 1px solid rgba(16, 34, 44, 0.08);
      margin-top: 16px;
    }
    .map-tooltip h4 {
      margin: 0 0 8px;
      font-size: 1.1rem;
    }
    .map-tooltip p {
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
    }
    .map-grid-line {
      stroke: rgba(16, 34, 44, 0.10);
      stroke-dasharray: 6 6;
    }
    .map-axis-label,
    .map-label,
    .axis-label,
    .legend-item {
      fill: var(--ink);
      font-size: 12px;
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
    }
    .map-dot {
      cursor: pointer;
      stroke: rgba(255,255,255,0.92);
      stroke-width: 2;
      transition: transform 160ms ease, opacity 160ms ease;
    }
    .map-dot:hover {
      transform: scale(1.08);
    }
    .map-dot--hub { fill: #164e63; }
    .map-dot--vulnerable { fill: #b91c1c; }
    .map-dot.is-selected {
      stroke: #f59e0b;
      stroke-width: 3;
    }
    .chart-svg {
      width: 100%;
      height: auto;
      display: block;
      margin-top: 10px;
    }
    .grid-line {
      stroke: rgba(16, 34, 44, 0.12);
      stroke-width: 1;
    }
    .figure-card {
      overflow: hidden;
      border-radius: 22px;
      border: 1px solid rgba(16, 34, 44, 0.08);
      background: rgba(255,255,255,0.90);
    }
    .figure-card img {
      display: block;
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      background: rgba(16, 34, 44, 0.05);
    }
    .figure-card h4 {
      margin: 14px 16px 8px;
    }
    .figure-card p {
      margin: 0 16px 18px;
      color: var(--muted);
      line-height: 1.6;
      font-size: 0.93rem;
    }
    .source-item {
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid rgba(16, 34, 44, 0.08);
      background: rgba(16, 34, 44, 0.04);
    }
    .source-item strong {
      display: block;
      margin-bottom: 6px;
      font-size: 0.83rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .source-item code {
      font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
      word-break: break-word;
      font-size: 0.88rem;
    }
    .footer-note {
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.7;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(14px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 1100px) {
      .hero-grid,
      .portfolio-grid,
      .geo-grid,
      .decision-grid,
      .insight-grid,
      .figure-grid,
      .source-grid {
        grid-template-columns: 1fr;
      }
      .metric-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .hero-signals,
      .data-cards {
        grid-template-columns: 1fr;
      }
    }
    @media (max-width: 680px) {
      .shell {
        width: min(100vw - 16px, 100%);
        padding-top: 16px;
      }
      .hero,
      .section {
        padding: 18px;
        border-radius: 22px;
      }
      .metric-grid {
        grid-template-columns: 1fr;
      }
      h1 {
        max-width: none;
      }
      .bar-row {
        grid-template-columns: 1fr;
      }
      .geo-map {
        min-height: auto;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-grid">
        <div>
          <p class="eyebrow">Research review</p>
          <h1>Copenhagen mobility resilience, turned into a decision-facing review.</h1>
          <p class="hero-copy">
            This page packages the repository's committed structure, robustness, and reliability outputs into one narrative:
            network shape, failure sensitivity, line-level delay exposure, and early transfer-risk decisions.
            It is meant to sit beside the atlas and benchmark as the evidence layer for people who need both presentation quality and methodological traceability.
          </p>
          <div class="nav-links">
            <a href="./index.html">Overview</a>
            <a href="./atlas.html">Atlas</a>
            <a href="./benchmark.html">Benchmark</a>
            <a class="active" href="./results.html">Research Review</a>
          </div>
          <div class="hero-tags">
            <span class="hero-tag">Static network evidence</span>
            <span class="hero-tag">Observed reliability</span>
            <span class="hero-tag">Risk-model context</span>
          </div>
        </div>
        <aside class="hero-panel">
          <h3>How to read this page</h3>
          <p>
            Start with the executive cards, then use the line portfolio explorer to isolate reliability outliers.
            The geographic panel highlights where structural exposure concentrates in the static network. The final
            section keeps routing and risk outputs visible so the polished narrative remains audit-friendly.
          </p>
        </aside>
      </div>
      <div class="hero-signals">
        <article class="signal-card">
          <h3>Reliability benchmark</h3>
          <p>__BEST_LINE_SIGNAL__</p>
        </article>
        <article class="signal-card">
          <h3>Intervention priority</h3>
          <p>__WORST_LINE_SIGNAL__</p>
        </article>
        <article class="signal-card">
          <h3>Coverage caveat</h3>
          <p>__COVERAGE_SIGNAL__</p>
        </article>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Executive View</h2>
          <p>High-level performance and exposure signals for management review.</p>
        </div>
      </div>
      <div class="metric-grid">__METRIC_CARDS__</div>
      <div class="insight-grid">__EXECUTIVE_CARDS__</div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Interactive Line Portfolio</h2>
          <p>Filter the reliability ranking, focus a single line, and compare its tail delay against the broader portfolio.</p>
        </div>
      </div>
      <div class="control-row">
        <div class="control">
          <label for="line-search">Search line</label>
          <input id="line-search" type="search" placeholder="E, Re 4516, IC 141">
        </div>
        <div class="control">
          <label for="band-filter">Performance band</label>
          <select id="band-filter">
            <option value="all">All bands</option>
            <option value="Leading">Leading</option>
            <option value="Stable">Stable</option>
            <option value="Watchlist">Watchlist</option>
            <option value="At Risk">At Risk</option>
            <option value="Critical">Critical</option>
          </select>
        </div>
        <div class="control">
          <label for="sort-filter">Sort by</label>
          <select id="sort-filter">
            <option value="p95_desc">Highest P95 first</option>
            <option value="p95_asc">Lowest P95 first</option>
            <option value="avg_desc">Highest average delay</option>
            <option value="n_desc">Largest sample size</option>
            <option value="rank_asc">Published rank</option>
          </select>
        </div>
      </div>
      <div class="portfolio-grid">
        <article class="panel">
          <div id="selected-line-summary"></div>
          <div id="selected-line-bars" class="line-bars"></div>
        </article>
        <article class="panel">
          <h3>Portfolio context</h3>
          <p class="panel-copy">The ranking chart responds to the active filter. Click a row to pin a line.</p>
          <div id="band-summary" class="data-cards"></div>
          <div id="ranking-chart" class="ranking-chart"></div>
        </article>
      </div>
      <div class="line-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Line</th>
              <th>Band</th>
              <th>Rank</th>
              <th>P50</th>
              <th>P90</th>
              <th>P95</th>
              <th>Average</th>
              <th>Samples</th>
            </tr>
          </thead>
          <tbody id="line-table-body"></tbody>
        </table>
      </div>
      <p id="line-table-note" class="table-note"></p>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Geographic Exposure</h2>
          <p>The map is a schematic coordinate view built from GTFS stop locations. It highlights where connectivity concentration and vulnerability overlap.</p>
        </div>
      </div>
      <div class="control-row">
        <label class="legend-pill legend-vulnerable"><input id="map-layer-vulnerable" type="checkbox" checked>Critical bridges</label>
        <label class="legend-pill legend-hub"><input id="map-layer-hub" type="checkbox" checked>Top connectivity hubs</label>
      </div>
      <div class="geo-grid">
        <article class="panel">
          <h3>Static network map</h3>
          <div id="geo-map" class="geo-map"></div>
          <p class="small-note">No external basemap is used. This view intentionally stays offline and reproducible inside the repo.</p>
        </article>
        <article class="panel">
          <h3>Selected node</h3>
          <div id="map-detail" class="map-tooltip"></div>
          <div class="legend-row">
            <span class="legend-pill legend-vulnerable">Critical bridges</span>
            <span class="legend-pill legend-hub">Top hubs</span>
          </div>
          <div class="line-table-wrap">__MAP_SUMMARY_TABLE__</div>
        </article>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Decision Support Layer</h2>
          <p>Static fragility, observed delay patterns, risk-model confidence, and route trade-offs are shown together so the research can support operational decisions.</p>
        </div>
      </div>
      <div class="decision-grid">
        <article class="panel">
          <h3>Failure sensitivity</h3>
          <p class="panel-copy">Largest connected component retention under random and targeted removals.</p>
          __CHECKPOINT_CHART__
          <h3 style="margin-top:18px;">Observed delay tail by hour</h3>
          <p class="panel-copy">P95 delay profile in Copenhagen local hour.</p>
          __HOUR_CHART__
        </article>
        <article class="panel">
          <h3>Mode-level risk model</h3>
          <p class="panel-copy">Current model remains mode-level with explicit fallback logic when sample sizes thin out.</p>
          __RISK_TABLE__
          <h3 style="margin-top:18px;">Router trade-off table</h3>
          <p class="panel-copy">Sample candidate paths show the travel time versus robustness trade-off.</p>
          __ROUTER_TABLE__
        </article>
      </div>
      <div class="figure-grid">__FIGURES__</div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Provenance</h2>
          <p>The dashboard is generated from committed markdown, CSV, JSON, and PNG artifacts so it remains auditable and safe to open locally.</p>
        </div>
      </div>
      <div class="source-grid">__SOURCE_GRID__</div>
      <p class="footer-note">
        Generated at __GENERATED_AT__. Build command:
        <code>python3 -m src.app.results_dashboard --out __OUTPUT_REL__</code>.
      </p>
    </section>
  </main>

  <script id="dashboard-data" type="application/json">__DASHBOARD_DATA__</script>
  <script>
    const dashboardData = JSON.parse(document.getElementById("dashboard-data").textContent);
    const lineState = {
      query: "",
      band: "all",
      sort: "p95_desc",
      selectedLine: dashboardData.portfolio.default_selected_line
    };
    const mapState = {
      selectedPointId: dashboardData.map.default_selected_point_id,
      layers: { vulnerable: true, hub: true }
    };

    const lineSearchEl = document.getElementById("line-search");
    const bandFilterEl = document.getElementById("band-filter");
    const sortFilterEl = document.getElementById("sort-filter");
    const selectedLineSummaryEl = document.getElementById("selected-line-summary");
    const selectedLineBarsEl = document.getElementById("selected-line-bars");
    const bandSummaryEl = document.getElementById("band-summary");
    const rankingChartEl = document.getElementById("ranking-chart");
    const lineTableBodyEl = document.getElementById("line-table-body");
    const lineTableNoteEl = document.getElementById("line-table-note");
    const geoMapEl = document.getElementById("geo-map");
    const mapDetailEl = document.getElementById("map-detail");
    const mapLayerVulnerableEl = document.getElementById("map-layer-vulnerable");
    const mapLayerHubEl = document.getElementById("map-layer-hub");

    function fmtInt(value) {
      return new Intl.NumberFormat("en-US").format(value);
    }

    function fmtSeconds(value) {
      return `${Math.round(value)}s`;
    }

    function fmtPct(value, decimals = 1) {
      return `${value.toFixed(decimals)}%`;
    }

    function bandClass(band) {
      return `tone-${band.toLowerCase().replace(/[^a-z]+/g, "-")}`;
    }

    function getFilteredLines() {
      const query = lineState.query.trim().toLowerCase();
      let rows = dashboardData.portfolio.reliability.filter((row) => {
        const queryMatch = !query || row.line.toLowerCase().includes(query);
        const bandMatch = lineState.band === "all" || row.band === lineState.band;
        return queryMatch && bandMatch;
      });

      const sorters = {
        p95_desc: (a, b) => b.p95_delay_sec - a.p95_delay_sec || b.avg_delay_sec - a.avg_delay_sec,
        p95_asc: (a, b) => a.p95_delay_sec - b.p95_delay_sec || a.avg_delay_sec - b.avg_delay_sec,
        avg_desc: (a, b) => b.avg_delay_sec - a.avg_delay_sec || b.p95_delay_sec - a.p95_delay_sec,
        n_desc: (a, b) => b.n - a.n || a.rank - b.rank,
        rank_asc: (a, b) => a.rank - b.rank
      };
      rows = rows.slice().sort(sorters[lineState.sort]);
      return rows;
    }

    function ensureSelectedLine(rows) {
      if (!rows.length) {
        return null;
      }
      const selected = rows.find((row) => row.line === lineState.selectedLine);
      if (selected) {
        return selected;
      }
      lineState.selectedLine = rows[0].line;
      return rows[0];
    }

    function renderSelectedLine(rows) {
      const selected = ensureSelectedLine(rows);
      if (!selected) {
        selectedLineSummaryEl.innerHTML = "<p class='small-note'>No lines match the current filter.</p>";
        selectedLineBarsEl.innerHTML = "";
        return;
      }

      const percentileOfWorst = Math.max(0, Math.min(100, (selected.p95_delay_sec / dashboardData.portfolio.worst_p95) * 100));
      const medianGap = selected.p95_delay_sec - dashboardData.portfolio.network_median_p95;
      selectedLineSummaryEl.innerHTML = `
        <div class="selected-banner">
          <div>
            <h3>${selected.line}</h3>
            <div class="selected-meta">Published rank #${selected.rank} of ${dashboardData.portfolio.reliability.length} tracked lines</div>
          </div>
          <span class="tone-pill ${bandClass(selected.band)}">${selected.band}</span>
        </div>
        <p class="panel-copy">Use this line view to compare one service against the rest of the portfolio. Positive numbers below indicate where delay tail or sample volume makes the line stand out.</p>
        <div class="data-cards">
          <div class="data-card">
            <div class="label">P95 delay</div>
            <div class="value">${fmtSeconds(selected.p95_delay_sec)}</div>
            <div class="meta">${medianGap >= 0 ? "+" : ""}${fmtSeconds(medianGap)} vs network median</div>
          </div>
          <div class="data-card">
            <div class="label">Average delay</div>
            <div class="value">${fmtSeconds(selected.avg_delay_sec)}</div>
            <div class="meta">Mean observed departure drift</div>
          </div>
          <div class="data-card">
            <div class="label">Sample size</div>
            <div class="value">${fmtInt(selected.n)}</div>
            <div class="meta">Underlying observations in the ranking table</div>
          </div>
          <div class="data-card">
            <div class="label">Relative to worst</div>
            <div class="value">${fmtPct(percentileOfWorst, 0)}</div>
            <div class="meta">P95 as a share of the current worst line tail</div>
          </div>
        </div>
      `;

      const percentiles = [
        { label: "P50", value: selected.p50_delay_sec, cls: "teal" },
        { label: "P90", value: selected.p90_delay_sec, cls: "amber" },
        { label: "P95", value: selected.p95_delay_sec, cls: "red" }
      ];
      selectedLineBarsEl.innerHTML = percentiles.map((item) => `
        <div class="bar-row">
          <div>${item.label}</div>
          <div class="bar-track">
            <div class="bar-fill bar-fill--${item.cls}" style="width:${Math.max(4, item.value / dashboardData.portfolio.worst_p95 * 100)}%"></div>
          </div>
          <div>${fmtSeconds(item.value)}</div>
        </div>
      `).join("");
    }

    function renderBandSummary(rows) {
      const counts = new Map(dashboardData.portfolio.band_order.map((band) => [band, 0]));
      rows.forEach((row) => counts.set(row.band, (counts.get(row.band) || 0) + 1));
      const totalSamples = rows.reduce((acc, row) => acc + row.n, 0);
      const maxP95 = rows.length ? Math.max(...rows.map((row) => row.p95_delay_sec)) : 0;
      bandSummaryEl.innerHTML = `
        <div class="data-card">
          <div class="label">Lines in view</div>
          <div class="value">${fmtInt(rows.length)}</div>
          <div class="meta">${fmtInt(totalSamples)} observations represented</div>
        </div>
        <div class="data-card">
          <div class="label">Critical</div>
          <div class="value">${fmtInt(counts.get("Critical") || 0)}</div>
          <div class="meta">Highest-priority outliers in current filter</div>
        </div>
        <div class="data-card">
          <div class="label">Leading</div>
          <div class="value">${fmtInt(counts.get("Leading") || 0)}</div>
          <div class="meta">Benchmark services in the active slice</div>
        </div>
        <div class="data-card">
          <div class="label">Max P95</div>
          <div class="value">${fmtSeconds(maxP95)}</div>
          <div class="meta">Upper tail currently visible</div>
        </div>
      `;
    }

    function renderRankingChart(rows) {
      const focusRows = rows.slice(0, 8);
      if (!focusRows.length) {
        rankingChartEl.innerHTML = "<p class='small-note'>No ranking rows to display.</p>";
        return;
      }
      rankingChartEl.innerHTML = focusRows.map((row) => `
        <div class="bar-row">
          <div><button class="line-button" data-line-select="${row.line}">${row.line}</button></div>
          <div class="bar-track">
            <div class="bar-fill bar-fill--red" style="width:${Math.max(4, row.p95_delay_sec / dashboardData.portfolio.worst_p95 * 100)}%"></div>
          </div>
          <div>${fmtSeconds(row.p95_delay_sec)}</div>
        </div>
      `).join("");
    }

    function renderLineTable(rows) {
      if (!rows.length) {
        lineTableBodyEl.innerHTML = "<tr><td colspan='8'>No lines match the current filter.</td></tr>";
        lineTableNoteEl.textContent = "Try broadening the band or clearing the search query.";
        return;
      }
      lineTableBodyEl.innerHTML = rows.map((row) => `
        <tr class="line-row ${row.line === lineState.selectedLine ? "is-selected" : ""}" data-line-select="${row.line}">
          <td><button class="line-button" data-line-select="${row.line}">${row.line}</button></td>
          <td><span class="tone-pill ${bandClass(row.band)}">${row.band}</span></td>
          <td>#${row.rank}</td>
          <td>${fmtSeconds(row.p50_delay_sec)}</td>
          <td>${fmtSeconds(row.p90_delay_sec)}</td>
          <td>${fmtSeconds(row.p95_delay_sec)}</td>
          <td>${fmtSeconds(row.avg_delay_sec)}</td>
          <td>${fmtInt(row.n)}</td>
        </tr>
      `).join("");
      lineTableNoteEl.textContent = `${rows.length} line(s) shown. Click a row to pin a line in the detail card.`;
    }

    function renderPortfolio() {
      const rows = getFilteredLines();
      renderSelectedLine(rows);
      renderBandSummary(rows);
      renderRankingChart(rows);
      renderLineTable(rows);
    }

    function getVisibleMapPoints() {
      return dashboardData.map.points.filter((point) => mapState.layers[point.layer]);
    }

    function ensureSelectedPoint(points) {
      if (!points.length) {
        return null;
      }
      const selected = points.find((point) => point.id === mapState.selectedPointId);
      if (selected) {
        return selected;
      }
      mapState.selectedPointId = points[0].id;
      return points[0];
    }

    function renderMap() {
      const points = getVisibleMapPoints();
      if (!points.length) {
        geoMapEl.innerHTML = "<p class='small-note'>No map layers selected.</p>";
        mapDetailEl.innerHTML = "<p>Select a layer to restore the spatial view.</p>";
        return;
      }

      const selected = ensureSelectedPoint(points);
      const width = 780;
      const height = 520;
      const pad = 42;
      const lons = dashboardData.map.points.map((point) => point.lon);
      const lats = dashboardData.map.points.map((point) => point.lat);
      const minLon = Math.min(...lons) - 0.35;
      const maxLon = Math.max(...lons) + 0.35;
      const minLat = Math.min(...lats) - 0.28;
      const maxLat = Math.max(...lats) + 0.28;
      const usableWidth = width - pad * 2;
      const usableHeight = height - pad * 2;

      function project(point) {
        const x = pad + ((point.lon - minLon) / (maxLon - minLon)) * usableWidth;
        const y = height - pad - ((point.lat - minLat) / (maxLat - minLat)) * usableHeight;
        return { x, y };
      }

      const grid = [];
      for (let i = 1; i < 4; i += 1) {
        const gx = pad + (usableWidth * i) / 4;
        const gy = pad + (usableHeight * i) / 4;
        grid.push(`<line x1="${gx}" y1="${pad}" x2="${gx}" y2="${height - pad}" class="map-grid-line"></line>`);
        grid.push(`<line x1="${pad}" y1="${gy}" x2="${width - pad}" y2="${gy}" class="map-grid-line"></line>`);
      }

      const labels = [
        { text: "Jutland", lon: 9.3, lat: 56.0 },
        { text: "Funen", lon: 10.2, lat: 55.4 },
        { text: "Zealand / CPH", lon: 12.0, lat: 55.7 }
      ].map((label) => {
        const point = project(label);
        return `<text x="${point.x}" y="${point.y}" class="map-label" opacity="0.55">${label.text}</text>`;
      }).join("");

      const dots = points.map((point) => {
        const projected = project(point);
        const radiusBase = point.layer === "vulnerable" ? 8 : 7;
        const score = Math.max(1, Number(point.primary_metric_value));
        const radius = Math.min(18, radiusBase + Math.log10(score + 1) * 2.5);
        return `<circle class="map-dot map-dot--${point.layer} ${point.id === selected.id ? "is-selected" : ""}"
                  data-point-id="${point.id}" cx="${projected.x}" cy="${projected.y}" r="${radius}"></circle>`;
      }).join("");

      geoMapEl.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Spatial concentration of vulnerable nodes and top hubs">
          <rect x="${pad}" y="${pad}" width="${usableWidth}" height="${usableHeight}" rx="24" fill="rgba(255,255,255,0.72)" stroke="rgba(16,34,44,0.10)"></rect>
          ${grid.join("")}
          ${labels}
          ${dots}
          <text x="${pad}" y="${pad - 12}" class="map-axis-label">lat</text>
          <text x="${width - pad}" y="${height - 10}" text-anchor="end" class="map-axis-label">lon</text>
        </svg>
      `;

      mapDetailEl.innerHTML = `
        <h4>${selected.label}</h4>
        <p><strong>${selected.primary_metric_label}:</strong> ${selected.primary_metric_value}</p>
        <p><strong>${selected.secondary_metric_label}:</strong> ${selected.secondary_metric_value}</p>
        <p><strong>Layer:</strong> ${selected.layer === "vulnerable" ? "Critical bridge" : "Top connectivity hub"}</p>
        <p>${selected.narrative}</p>
      `;
    }

    function renderAll() {
      renderPortfolio();
      renderMap();
    }

    lineSearchEl.addEventListener("input", (event) => {
      lineState.query = event.target.value;
      renderPortfolio();
    });
    bandFilterEl.addEventListener("change", (event) => {
      lineState.band = event.target.value;
      renderPortfolio();
    });
    sortFilterEl.addEventListener("change", (event) => {
      lineState.sort = event.target.value;
      renderPortfolio();
    });

    document.addEventListener("click", (event) => {
      const lineButton = event.target.closest("[data-line-select]");
      if (lineButton) {
        lineState.selectedLine = lineButton.getAttribute("data-line-select");
        renderPortfolio();
      }

      const mapPoint = event.target.closest("[data-point-id]");
      if (mapPoint) {
        mapState.selectedPointId = mapPoint.getAttribute("data-point-id");
        renderMap();
      }
    });

    mapLayerVulnerableEl.addEventListener("change", (event) => {
      mapState.layers.vulnerable = event.target.checked;
      renderMap();
    });
    mapLayerHubEl.addEventListener("change", (event) => {
      mapState.layers.hub = event.target.checked;
      renderMap();
    });

    renderAll();
  </script>
</body>
</html>
"""

    output_rel = _rel_href(output_path, repo_root)
    html_output = (
        template.replace(
            "__BEST_LINE_SIGNAL__",
            _escape(
                f"{best_line['line']} currently anchors the reliable end of the portfolio with a { _fmt_seconds(best_line['p95_delay_sec']) } P95 tail."
            ),
        )
        .replace(
            "__WORST_LINE_SIGNAL__",
            _escape(
                f"{worst_line['line']} should be the first candidate for targeted intervention, with a { _fmt_seconds(worst_line['p95_delay_sec']) } P95 tail."
            ),
        )
        .replace(
            "__COVERAGE_SIGNAL__",
            _escape(
                f"The committed 24h Task A summary shows { _fmt_ratio_pct(week3_summary['sampling_24h']['coverage_ratio'], 1) } coverage, so operational completeness should still be read alongside the seven-day conclusions."
            ),
        )
        .replace("__METRIC_CARDS__", metric_cards)
        .replace("__EXECUTIVE_CARDS__", executive_cards)
        .replace("__MAP_SUMMARY_TABLE__", map_summary_table)
        .replace("__CHECKPOINT_CHART__", checkpoint_chart)
        .replace("__HOUR_CHART__", hour_chart)
        .replace("__RISK_TABLE__", risk_table)
        .replace("__ROUTER_TABLE__", router_table)
        .replace("__FIGURES__", figures)
        .replace("__SOURCE_GRID__", source_grid)
        .replace("__GENERATED_AT__", _escape(utc_now_iso()))
        .replace("__OUTPUT_REL__", _escape(output_rel))
        .replace("__DASHBOARD_DATA__", _json_script(dashboard_data))
    )
    return html_output


def render_dashboard(repo_root: Path, output_path: Path) -> Path:
    ensure_parent(output_path)
    try:
      html_doc = build_dashboard_html(repo_root, output_path)
    except Exception as exc:  # pragma: no cover
      html_doc = _build_unavailable_dashboard_html(repo_root, output_path, exc)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a static research-results dashboard HTML page")
    parser.add_argument("--repo-root", default=None, help="Repository root; defaults to the current project root")
    parser.add_argument(
        "--out",
        default=None,
        help="Output HTML path; defaults to web/accessibility/results.html under the repo root",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else _repo_root()
    output_path = Path(args.out).resolve() if args.out else repo_root / "web" / "accessibility" / "results.html"
    render_dashboard(repo_root, output_path)
    print(f"wrote dashboard: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
