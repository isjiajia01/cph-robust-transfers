from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict, deque
from pathlib import Path

from src.common.io import write_csv


def load_undirected_graph(edges_path: Path) -> dict[str, set[str]]:
    g: dict[str, set[str]] = defaultdict(set)
    with edges_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            a = r["from_stop_id"]
            b = r["to_stop_id"]
            g[a].add(b)
            g[b].add(a)
    return g


def _component_labels(g: dict[str, set[str]]) -> tuple[dict[str, int], dict[int, int]]:
    labels: dict[str, int] = {}
    comp_sizes: dict[int, int] = {}
    cid = 0
    for start in g:
        if start in labels:
            continue
        q = deque([start])
        labels[start] = cid
        size = 0
        while q:
            cur = q.popleft()
            size += 1
            for nxt in g[cur]:
                if nxt not in labels:
                    labels[nxt] = cid
                    q.append(nxt)
        comp_sizes[cid] = size
        cid += 1
    return labels, comp_sizes


def giant_component_size(g: dict[str, set[str]]) -> int:
    _, comp_sizes = _component_labels(g)
    return max(comp_sizes.values()) if comp_sizes else 0


def _largest_component_nodes(g: dict[str, set[str]]) -> set[str]:
    labels, comp_sizes = _component_labels(g)
    if not comp_sizes:
        return set()
    best_cid = max(comp_sizes.items(), key=lambda x: x[1])[0]
    return {n for n, cid in labels.items() if cid == best_cid}


def _remove_nodes(g: dict[str, set[str]], nodes_set: set[str]) -> dict[str, set[str]]:
    keep = {n for n in g if n not in nodes_set}
    ng: dict[str, set[str]] = {}
    for n in keep:
        ng[n] = {m for m in g[n] if m in keep}
    return ng


def _target_order_degree(g: dict[str, set[str]]) -> list[str]:
    return [n for n, _ in sorted(((n, len(nei)) for n, nei in g.items()), key=lambda x: x[1], reverse=True)]


def _approx_betweenness(g: dict[str, set[str]], max_sources: int, seed: int) -> dict[str, float]:
    nodes = sorted(g.keys())
    if not nodes:
        return {}
    rnd = random.Random(seed)
    if max_sources <= 0 or max_sources >= len(nodes):
        sources = nodes
    else:
        sources = rnd.sample(nodes, max_sources)

    cb = {v: 0.0 for v in nodes}
    for s in sources:
        stack: list[str] = []
        pred: dict[str, list[str]] = {v: [] for v in nodes}
        sigma = {v: 0.0 for v in nodes}
        sigma[s] = 1.0
        dist = {v: -1 for v in nodes}
        dist[s] = 0

        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in g[v]:
                if dist[w] < 0:
                    q.append(w)
                    dist[w] = dist[v] + 1
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        delta = {v: 0.0 for v in nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w] > 0:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                cb[w] += delta[w]

    scale = len(nodes) / len(sources)
    for v in cb:
        cb[v] *= scale
    return cb


def _target_order_betweenness(g: dict[str, set[str]], max_sources: int, seed: int) -> list[str]:
    cb = _approx_betweenness(g, max_sources=max_sources, seed=seed)
    return [n for n, _ in sorted(cb.items(), key=lambda x: x[1], reverse=True)]


def _reachable_od_ratio(g: dict[str, set[str]], od_pairs: list[tuple[str, str]]) -> float:
    if not od_pairs:
        return 0.0
    labels, _ = _component_labels(g)
    ok = 0
    total = 0
    for a, b in od_pairs:
        if a not in labels or b not in labels:
            total += 1
            continue
        total += 1
        if labels[a] == labels[b]:
            ok += 1
    return ok / total if total else 0.0


def _avg_shortest_path_lcc(g: dict[str, set[str]], max_sources: int, seed: int) -> float:
    lcc_nodes = list(_largest_component_nodes(g))
    if len(lcc_nodes) <= 1:
        return 0.0
    rnd = random.Random(seed)
    if max_sources <= 0 or max_sources >= len(lcc_nodes):
        sources = lcc_nodes
    else:
        sources = rnd.sample(lcc_nodes, max_sources)

    lcc_set = set(lcc_nodes)
    total_dist = 0
    total_cnt = 0

    for s in sources:
        q = deque([(s, 0)])
        seen = {s}
        while q:
            cur, d = q.popleft()
            if cur != s:
                total_dist += d
                total_cnt += 1
            for nxt in g[cur]:
                if nxt in lcc_set and nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, d + 1))

    return (total_dist / total_cnt) if total_cnt else 0.0


def _sample_od_pairs(nodes: list[str], n_pairs: int, seed: int) -> list[tuple[str, str]]:
    rnd = random.Random(seed)
    if len(nodes) < 2 or n_pairs <= 0:
        return []
    pairs = []
    for _ in range(n_pairs):
        a, b = rnd.sample(nodes, 2)
        pairs.append((a, b))
    return pairs


def run_simulation(
    g: dict[str, set[str]],
    strategy: str,
    k_values: list[int],
    repeats: int,
    seed: int,
    targeting: str = "betweenness",
    od_pairs: list[tuple[str, str]] | None = None,
    avgsp_sources: int = 12,
    betweenness_sources: int = 128,
) -> list[dict]:
    rnd = random.Random(seed)
    n = len(g)
    base_lcc = max(1, giant_component_size(g))

    if strategy == "targeted":
        if targeting == "betweenness":
            target_order = _target_order_betweenness(g, max_sources=betweenness_sources, seed=seed)
        else:
            target_order = _target_order_degree(g)
    else:
        target_order = []

    rows: list[dict] = []

    for k in k_values:
        remove_count = max(0, min(n, int((k / 100.0) * n)))
        for r in range(repeats):
            if strategy == "random":
                nodes = sorted(g.keys())
                rnd.shuffle(nodes)
                removed_set = set(nodes[:remove_count])
            else:
                removed_set = set(target_order[:remove_count])

            ng = _remove_nodes(g, removed_set)
            lcc = giant_component_size(ng) if ng else 0
            reach = _reachable_od_ratio(ng, od_pairs or []) if ng else 0.0
            avg_sp = _avg_shortest_path_lcc(ng, max_sources=avgsp_sources, seed=seed + r + k) if ng else 0.0

            rows.append(
                {
                    "run_id": f"{strategy}_{targeting}_{k}_{r}",
                    "strategy": strategy,
                    "targeting": targeting if strategy == "targeted" else "random",
                    "k_pct": k,
                    "seed": seed,
                    "lcc_ratio": round(lcc / base_lcc, 6),
                    "reachable_od_ratio": round(reach, 6),
                    "avg_shortest_path": round(avg_sp, 6),
                    "remaining_nodes": len(ng),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run robustness simulations")
    parser.add_argument("--edges", required=True, help="edges.csv path")
    parser.add_argument("--out", default="data/robustness/latest")
    parser.add_argument("--k-max", type=int, default=30)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--targeting", choices=["degree", "betweenness"], default="betweenness")
    parser.add_argument("--od-pairs", type=int, default=2000)
    parser.add_argument("--avgsp-sources", type=int, default=12)
    parser.add_argument("--betweenness-sources", type=int, default=128)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    g = load_undirected_graph(Path(args.edges))
    ks = list(range(args.step, args.k_max + 1, args.step))
    od_pairs = _sample_od_pairs(sorted(g.keys()), n_pairs=args.od_pairs, seed=args.seed)

    rows_random = run_simulation(
        g,
        "random",
        ks,
        args.repeats,
        args.seed,
        targeting=args.targeting,
        od_pairs=od_pairs,
        avgsp_sources=args.avgsp_sources,
        betweenness_sources=args.betweenness_sources,
    )
    rows_targeted = run_simulation(
        g,
        "targeted",
        ks,
        1,
        args.seed,
        targeting=args.targeting,
        od_pairs=od_pairs,
        avgsp_sources=args.avgsp_sources,
        betweenness_sources=args.betweenness_sources,
    )

    fieldnames = [
        "run_id",
        "strategy",
        "targeting",
        "k_pct",
        "seed",
        "lcc_ratio",
        "reachable_od_ratio",
        "avg_shortest_path",
        "remaining_nodes",
    ]
    write_csv(out_dir / "robustness_runs.csv", rows_random + rows_targeted, fieldnames)
    print(out_dir / "robustness_runs.csv")


if __name__ == "__main__":
    main()
