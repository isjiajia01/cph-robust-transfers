from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict, deque
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.common.io import write_csv
from src.robustness.simulate_failures import _approx_betweenness, load_undirected_graph


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _giant_component_size(g: dict[str, set[str]]) -> int:
    seen: set[str] = set()
    best = 0
    for start in g:
        if start in seen:
            continue
        q = deque([start])
        seen.add(start)
        size = 0
        while q:
            cur = q.popleft()
            size += 1
            for nxt in g[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        best = max(best, size)
    return best


def _remove_one(g: dict[str, set[str]], node: str) -> dict[str, set[str]]:
    keep = {n for n in g if n != node}
    return {n: {m for m in g[n] if m in keep} for n in keep}


def _percentiles(vals: list[float]) -> tuple[float, float, float]:
    if not vals:
        return 0.0, 0.0, 0.0
    v = sorted(vals)
    p50 = v[len(v) // 2]
    p10 = v[max(0, int(len(v) * 0.10) - 1)]
    p90 = v[min(len(v) - 1, int(len(v) * 0.90))]
    return p50, p10, p90


def _summarize_runs(runs: list[dict[str, str]]) -> list[dict]:
    grouped: dict[tuple[str, str, int], list[dict[str, float]]] = defaultdict(list)
    for r in runs:
        grouped[(r["strategy"], r.get("targeting", ""), int(r["k_pct"]))].append(
            {
                "lcc_ratio": float(r["lcc_ratio"]),
                "reachable_od_ratio": float(r.get("reachable_od_ratio", 0.0)),
                "avg_shortest_path": float(r.get("avg_shortest_path", 0.0)),
            }
        )

    rows: list[dict] = []
    for (strategy, targeting, k_pct), vals in sorted(grouped.items(), key=lambda x: (x[0][2], x[0][0])):
        lcc = [x["lcc_ratio"] for x in vals]
        ro = [x["reachable_od_ratio"] for x in vals]
        asp = [x["avg_shortest_path"] for x in vals if x["avg_shortest_path"] > 0]

        lcc_p50, lcc_p10, lcc_p90 = _percentiles(lcc)
        ro_p50, ro_p10, ro_p90 = _percentiles(ro)
        asp_p50, asp_p10, asp_p90 = _percentiles(asp)

        rows.append(
            {
                "strategy": strategy,
                "targeting": targeting,
                "k_pct": k_pct,
                "lcc_ratio_avg": round(sum(lcc) / len(lcc), 6),
                "lcc_ratio_p50": round(lcc_p50, 6),
                "lcc_ratio_p10": round(lcc_p10, 6),
                "lcc_ratio_p90": round(lcc_p90, 6),
                "reachable_od_ratio_avg": round(sum(ro) / len(ro), 6),
                "reachable_od_ratio_p50": round(ro_p50, 6),
                "reachable_od_ratio_p10": round(ro_p10, 6),
                "reachable_od_ratio_p90": round(ro_p90, 6),
                "avg_shortest_path_avg": round(sum(asp) / len(asp), 6) if asp else 0.0,
                "avg_shortest_path_p50": round(asp_p50, 6),
                "avg_shortest_path_p10": round(asp_p10, 6),
                "avg_shortest_path_p90": round(asp_p90, 6),
                "runs": len(vals),
            }
        )
    return rows


def _plot_lcc(summary_rows: list[dict], out_path: Path) -> None:
    by_strategy: dict[str, list[tuple[int, float, float, float]]] = defaultdict(list)
    for r in summary_rows:
        by_strategy[r["strategy"]].append((r["k_pct"], r["lcc_ratio_avg"], r["lcc_ratio_p10"], r["lcc_ratio_p90"]))

    plt.figure(figsize=(10, 5))
    colors = {"random": "#2f6db3", "targeted": "#c75b39"}

    for strategy in ("random", "targeted"):
        rows = sorted(by_strategy.get(strategy, []), key=lambda x: x[0])
        if not rows:
            continue
        x = [r[0] for r in rows]
        y = [r[1] for r in rows]
        y_low = [r[2] for r in rows]
        y_high = [r[3] for r in rows]
        plt.plot(x, y, marker="o", label=strategy, color=colors.get(strategy, "#333333"))
        if strategy == "random":
            plt.fill_between(x, y_low, y_high, color=colors[strategy], alpha=0.2)

    plt.xlabel("Removed nodes (%)")
    plt.ylabel("Largest component ratio")
    plt.title("Week2: Random Failure vs Targeted Attack (LCC)")
    plt.ylim(0, 1.05)
    plt.grid(alpha=0.25)
    plt.legend()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def _plot_extra_metrics(summary_rows: list[dict], out_path: Path) -> None:
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for r in summary_rows:
        by_strategy[r["strategy"]].append(r)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    colors = {"random": "#2f6db3", "targeted": "#c75b39"}

    for strategy in ("random", "targeted"):
        rows = sorted(by_strategy.get(strategy, []), key=lambda x: x["k_pct"])
        if not rows:
            continue
        x = [r["k_pct"] for r in rows]
        y_reach = [r["reachable_od_ratio_avg"] for r in rows]
        y_asp = [r["avg_shortest_path_avg"] for r in rows]

        axes[0].plot(x, y_reach, marker="o", label=strategy, color=colors[strategy])
        axes[1].plot(x, y_asp, marker="o", label=strategy, color=colors[strategy])

    axes[0].set_title("Reachable OD Ratio")
    axes[0].set_xlabel("Removed nodes (%)")
    axes[0].set_ylabel("Reachable OD ratio")
    axes[0].set_ylim(0, 1.05)
    axes[0].grid(alpha=0.25)

    axes[1].set_title("Average Shortest Path (LCC)")
    axes[1].set_xlabel("Removed nodes (%)")
    axes[1].set_ylabel("Avg shortest path")
    axes[1].grid(alpha=0.25)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2)
    plt.tight_layout(rect=[0, 0, 1, 0.92])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()


def _critical_nodes(
    g: dict[str, set[str]],
    nodes_metrics: list[dict[str, str]],
    top_n: int,
    k_out: int,
    betweenness_sources: int,
    seed: int,
) -> list[dict]:
    base = max(1, _giant_component_size(g))
    by_stop = {r["stop_id"]: r for r in nodes_metrics}
    cb = _approx_betweenness(g, max_sources=betweenness_sources, seed=seed)
    ranked_cb = sorted(cb.items(), key=lambda x: x[1], reverse=True)
    candidates = [stop_id for stop_id, _ in ranked_cb[:top_n]]

    impacts: list[dict] = []
    for stop_id in candidates:
        ng = _remove_one(g, stop_id)
        lcc = _giant_component_size(ng) if ng else 0
        delta = 1.0 - (lcc / base)
        metric_row = by_stop.get(stop_id)
        degree = 0
        if metric_row:
            degree = int(metric_row.get("in_degree", 0)) + int(metric_row.get("out_degree", 0))
        impacts.append(
            {
                "stop_id": stop_id,
                "degree": degree,
                "betweenness_score": round(cb.get(stop_id, 0.0), 6),
                "impact_delta_lcc": round(delta, 6),
                "planning_implication": _planning_implication(degree, cb.get(stop_id, 0.0), delta),
            }
        )

    impacts.sort(key=lambda x: x["impact_delta_lcc"], reverse=True)
    out = []
    for i, row in enumerate(impacts[:k_out], start=1):
        out.append({"rank": i, **row})
    return out


def _planning_implication(degree: int, betweenness_score: float, impact_delta_lcc: float) -> str:
    if impact_delta_lcc >= 0.2:
        return "High single-point failure risk; prioritize redundancy or fallback transfer options."
    if betweenness_score >= 0.02:
        return "Likely transfer bridge; monitor cross-line dependency and disruption spillover."
    if degree >= 8:
        return "High-connectivity hub; candidate for capacity protection and passenger flow hardening."
    return "Localized vulnerability; validate with service pattern and nearby stop substitution."


def _read_graph_manifest(edges_path: Path) -> dict:
    manifest_path = edges_path.parent / "graph_manifest.json"
    if not manifest_path.exists():
        return {}
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_results_summary(
    out_path: Path,
    summary_rows: list[dict],
    critical_rows: list[dict],
    graph_manifest: dict,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    targeted = [r for r in summary_rows if r["strategy"] == "targeted"]
    random_rows = [r for r in summary_rows if r["strategy"] == "random"]
    targeted_by_k = {int(r["k_pct"]): r for r in targeted}
    random_by_k = {int(r["k_pct"]): r for r in random_rows}
    anchor_ks = [k for k in (9, 15, 30) if k in targeted_by_k and k in random_by_k]
    data_date = graph_manifest.get("data_date") or Path(str(graph_manifest.get("gtfs_dir", ""))).name
    node_count = graph_manifest.get("node_count", graph_manifest.get("stop_count_filtered", 0))
    edge_count = graph_manifest.get("edge_count", graph_manifest.get("edge_count_filtered", 0))

    with out_path.open("w", encoding="utf-8") as f:
        f.write("# Robustness Summary\n\n")
        if graph_manifest:
            f.write("## Graph Build\n")
            f.write(f"- Data date: `{data_date}`\n")
            f.write(f"- GTFS feed version: `{graph_manifest.get('gtfs_feed_version', '')}`\n")
            f.write(f"- Nodes / edges: `{node_count}` / `{edge_count}`\n")
            f.write(f"- Build params hash: `{graph_manifest.get('build_params_hash', '')}`\n")
            f.write("\n")

        f.write("## Read This Output\n")
        f.write("- Compare targeted vs random decay: faster targeted drop implies hub-dependent fragility.\n")
        f.write("- Read `impact_delta_lcc` as the single-node connectivity loss if that node disappears.\n")
        f.write("- Use the planning implication column as a first-pass narrative, not a final intervention recommendation.\n")
        f.write("\n")

        f.write("## Random vs Targeted Checkpoints\n")
        for k in anchor_ks:
            rand = random_by_k[k]
            tgt = targeted_by_k[k]
            f.write(
                f"- At `{k}%` removal: random LCC avg=`{rand['lcc_ratio_avg']}`, "
                f"targeted LCC avg=`{tgt['lcc_ratio_avg']}`\n"
            )
        if not anchor_ks:
            f.write("- No standard checkpoints available in current summary rows.\n")
        f.write("\n")

        f.write("## Top-10 Vulnerable Hubs\n")
        for row in critical_rows:
            f.write(
                f"- #{row['rank']} `{row['stop_id']}`: degree=`{row['degree']}`, "
                f"betweenness=`{row['betweenness_score']}`, impact_delta_lcc=`{row['impact_delta_lcc']}`, "
                f"implication={row['planning_implication']}\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Week2 robustness figures and critical nodes")
    parser.add_argument("--runs", required=True, help="robustness_runs.csv")
    parser.add_argument("--edges", required=True, help="edges.csv")
    parser.add_argument("--nodes", required=True, help="nodes.csv")
    parser.add_argument("--summary", default="data/robustness/20260302/robustness_summary.csv")
    parser.add_argument("--curve-png", default="docs/figures/week2_random_vs_targeted.png")
    parser.add_argument("--extra-png", default="docs/figures/week2_extra_metrics.png")
    parser.add_argument("--critical-out", default="data/robustness/20260302/critical_nodes_top10.csv")
    parser.add_argument("--results-dir", default="results/robustness")
    parser.add_argument("--results-summary-md", default="results/robustness/summary.md")
    parser.add_argument("--critical-top-n", type=int, default=300)
    parser.add_argument("--betweenness-sources", type=int, default=96)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    runs = _read_csv(Path(args.runs))
    summary_rows = _summarize_runs(runs)
    write_csv(
        Path(args.summary),
        summary_rows,
        [
            "strategy",
            "targeting",
            "k_pct",
            "lcc_ratio_avg",
            "lcc_ratio_p50",
            "lcc_ratio_p10",
            "lcc_ratio_p90",
            "reachable_od_ratio_avg",
            "reachable_od_ratio_p50",
            "reachable_od_ratio_p10",
            "reachable_od_ratio_p90",
            "avg_shortest_path_avg",
            "avg_shortest_path_p50",
            "avg_shortest_path_p10",
            "avg_shortest_path_p90",
            "runs",
        ],
    )

    _plot_lcc(summary_rows, Path(args.curve_png))
    _plot_extra_metrics(summary_rows, Path(args.extra_png))

    g = load_undirected_graph(Path(args.edges))
    nodes = _read_csv(Path(args.nodes))
    critical = _critical_nodes(
        g,
        nodes,
        top_n=args.critical_top_n,
        k_out=10,
        betweenness_sources=args.betweenness_sources,
        seed=args.seed,
    )
    write_csv(
        Path(args.critical_out),
        critical,
        ["rank", "stop_id", "degree", "betweenness_score", "impact_delta_lcc", "planning_implication"],
    )

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(args.curve_png), results_dir / "random_vs_targeted_curve.png")
    shutil.copy2(Path(args.extra_png), results_dir / "extra_metrics_curve.png")
    shutil.copy2(Path(args.critical_out), results_dir / "top10_vulnerable_nodes.csv")
    hub_src = Path("docs/figures/week1_top_hubs.png")
    if hub_src.exists():
        shutil.copy2(hub_src, results_dir / "key_hubs_map.png")
    graph_manifest = _read_graph_manifest(Path(args.edges))
    if graph_manifest:
        with (results_dir / "graph_manifest.json").open("w", encoding="utf-8") as f:
            json.dump(graph_manifest, f, ensure_ascii=True, indent=2)
    _write_results_summary(Path(args.results_summary_md), summary_rows, critical, graph_manifest)
    readme = results_dir / "README.md"
    with readme.open("w", encoding="utf-8") as f:
        f.write("# Robustness Results\n\n")
        f.write("- `key_hubs_map.png`: baseline hub ranking proxy from Week1.\n")
        f.write("- `random_vs_targeted_curve.png`: LCC ratio vs removed-node percentage.\n")
        f.write("- `extra_metrics_curve.png`: reachable OD ratio and average shortest path trends.\n")
        f.write("- `top10_vulnerable_nodes.csv`: nodes with highest single-node LCC impact.\n")
        f.write("- `summary.md`: fixed narrative summary for interview/demo use.\n")
        f.write("- `graph_manifest.json`: graph build metadata and filtering rules.\n")
        f.write("- Read targeted vs random as fragility evidence: faster targeted decay implies hub bottlenecks.\n")
        f.write("- Use top-10 table with planning implication notes to map candidate interventions.\n")
        f.write("- Curves are comparable only under the same graph build + simulation params.\n")
        f.write("- Re-run from scripts to keep web/portfolio artifacts reproducible.\n")

    print(args.summary)
    print(args.curve_png)
    print(args.extra_png)
    print(args.critical_out)
    print(args.results_summary_md)
    print(results_dir)


if __name__ == "__main__":
    main()
