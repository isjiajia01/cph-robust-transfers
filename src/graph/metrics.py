from __future__ import annotations

import argparse
import csv
from collections import defaultdict, deque
from pathlib import Path

from src.common.io import write_csv


def _read_edges(path: Path) -> list[tuple[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [(r["from_stop_id"], r["to_stop_id"]) for r in reader]


def _closeness(node: str, adj: dict[str, set[str]]) -> float:
    q = deque([(node, 0)])
    seen = {node}
    dist_sum = 0
    reachable = 0

    while q:
        cur, d = q.popleft()
        for nxt in adj[cur]:
            if nxt in seen:
                continue
            seen.add(nxt)
            reachable += 1
            dist_sum += d + 1
            q.append((nxt, d + 1))

    if dist_sum == 0:
        return 0.0
    return reachable / dist_sum


def compute_metrics(edges: list[tuple[str, str]]) -> list[dict]:
    adj: dict[str, set[str]] = defaultdict(set)
    indeg: dict[str, int] = defaultdict(int)
    outdeg: dict[str, int] = defaultdict(int)

    for a, b in edges:
        adj[a].add(b)
        _ = adj[b]
        indeg[b] += 1
        outdeg[a] += 1

    rows: list[dict] = []
    for n in sorted(adj):
        rows.append(
            {
                "stop_id": n,
                "in_degree": indeg.get(n, 0),
                "out_degree": outdeg.get(n, 0),
                "closeness": round(_closeness(n, adj), 6),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute graph metrics from edges.csv")
    parser.add_argument("--edges", required=True)
    parser.add_argument("--out", default="data/graph/latest/metrics.csv")
    args = parser.parse_args()

    rows = compute_metrics(_read_edges(Path(args.edges)))
    write_csv(Path(args.out), rows, ["stop_id", "in_degree", "out_degree", "closeness"])
    print(args.out)


if __name__ == "__main__":
    main()
