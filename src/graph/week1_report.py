from __future__ import annotations

import argparse
import csv
from collections import defaultdict, deque
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def component_sizes(edges: list[tuple[str, str]]) -> list[int]:
    g: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        g[a].add(b)
        g[b].add(a)

    seen: set[str] = set()
    sizes: list[int] = []
    for n in g:
        if n in seen:
            continue
        q = deque([n])
        seen.add(n)
        sz = 0
        while q:
            cur = q.popleft()
            sz += 1
            for nxt in g[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        sizes.append(sz)
    sizes.sort(reverse=True)
    return sizes


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Week1 hub/connectivity figures and summary")
    parser.add_argument("--parsed-dir", required=True)
    parser.add_argument("--graph-dir", required=True)
    parser.add_argument("--fig-dir", default="docs/figures")
    parser.add_argument("--summary", default="docs/week1_summary.md")
    args = parser.parse_args()

    parsed_dir = Path(args.parsed_dir)
    graph_dir = Path(args.graph_dir)
    fig_dir = Path(args.fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    stops = read_csv(parsed_dir / "stops.csv")
    nodes = read_csv(graph_dir / "nodes.csv")
    edges_raw = read_csv(graph_dir / "edges.csv")

    stop_name = {r["stop_id"]: r.get("stop_name", r["stop_id"]) for r in stops}

    ranked = []
    for n in nodes:
        indeg = int(n.get("in_degree", "0") or 0)
        outdeg = int(n.get("out_degree", "0") or 0)
        ranked.append((n["stop_id"], indeg + outdeg, indeg, outdeg))
    ranked.sort(key=lambda x: x[1], reverse=True)
    top10 = ranked[:10]

    labels = [stop_name.get(stop_id, stop_id)[:24] for stop_id, *_ in top10]
    values = [v for _, v, _, _ in top10]

    plt.figure(figsize=(12, 5))
    plt.bar(labels, values, color="#2f6db3")
    plt.xticks(rotation=35, ha="right")
    plt.ylabel("Total degree (in+out)")
    plt.title("Week1: Top-10 Hub Stops by Degree")
    plt.tight_layout()
    hub_fig = fig_dir / "week1_top_hubs.png"
    plt.savefig(hub_fig, dpi=150)
    plt.close()

    edge_pairs = [(r["from_stop_id"], r["to_stop_id"]) for r in edges_raw]
    sizes = component_sizes(edge_pairs)
    top_comp = sizes[:20]

    plt.figure(figsize=(10, 4))
    plt.plot(range(1, len(top_comp) + 1), top_comp, marker="o", color="#c75b39")
    plt.xlabel("Component rank")
    plt.ylabel("Nodes in component")
    plt.title("Week1: Connected Component Size Distribution (Top 20)")
    plt.tight_layout()
    comp_fig = fig_dir / "week1_component_sizes.png"
    plt.savefig(comp_fig, dpi=150)
    plt.close()

    lcc = top_comp[0] if top_comp else 0
    stop_count = len(nodes)
    edge_count = len(edges_raw)
    lcc_ratio = (lcc / stop_count) if stop_count else 0.0

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        f.write("# Week1 Summary\n\n")
        f.write(f"- Stops (nodes): {stop_count}\n")
        f.write(f"- Directed edges: {edge_count}\n")
        f.write(f"- Largest connected component size: {lcc} ({lcc_ratio:.2%})\n")
        f.write("\n## Top-10 hubs by degree\n")
        for stop_id, deg, indeg, outdeg in top10:
            name = stop_name.get(stop_id, stop_id)
            f.write(f"- {name} (`{stop_id}`): degree={deg}, in={indeg}, out={outdeg}\n")
        f.write("\n## Figures\n")
        f.write(f"- {hub_fig.as_posix()}\n")
        f.write(f"- {comp_fig.as_posix()}\n")

    print(summary_path)
    print(hub_fig)
    print(comp_fig)


if __name__ == "__main__":
    main()
