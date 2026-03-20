from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from src.common.io import write_csv
from src.common.time_utils import hhmmss_to_seconds


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _build_edges_internal(gtfs_dir: Path) -> tuple[list[dict], list[dict], dict[str, int]]:
    trips = _read_csv(gtfs_dir / "trips.csv")
    stop_times = _read_csv(gtfs_dir / "stop_times.csv")
    stops_path = gtfs_dir / "stops.csv"
    stops = _read_csv(stops_path) if stops_path.exists() else []

    trip_route = {r["trip_id"]: r.get("route_id", "") for r in trips}

    by_trip: dict[str, list[dict]] = defaultdict(list)
    for row in stop_times:
        by_trip[row["trip_id"]].append(row)

    edge_samples_raw: dict[tuple[str, str], list[int]] = defaultdict(list)
    edge_routes: dict[tuple[str, str], set[str]] = defaultdict(set)

    for trip_id, rows in by_trip.items():
        rows.sort(key=lambda r: int(r["stop_sequence"]))
        for prev, curr in zip(rows, rows[1:]):
            from_stop = prev["stop_id"]
            to_stop = curr["stop_id"]
            dep = hhmmss_to_seconds(prev["departure_time"])
            arr = hhmmss_to_seconds(curr["arrival_time"])
            travel_sec = max(0, arr - dep)
            key = (from_stop, to_stop)
            edge_samples_raw[key].append(travel_sec)
            edge_routes[key].add(trip_route.get(trip_id, ""))

    edge_samples = {k: v for k, v in edge_samples_raw.items() if k[0] != k[1]}
    edges: list[dict] = []
    in_deg: dict[str, int] = defaultdict(int)
    out_deg: dict[str, int] = defaultdict(int)

    for (from_stop, to_stop), samples in edge_samples_raw.items():
        if from_stop == to_stop:
            continue
        out_deg[from_stop] += 1
        in_deg[to_stop] += 1
        edges.append(
            {
                "from_stop_id": from_stop,
                "to_stop_id": to_stop,
                "scheduled_travel_sec_p50": int(median(samples)),
                "trip_count": len(samples),
                "route_ids": "|".join(sorted(x for x in edge_routes[(from_stop, to_stop)] if x)),
            }
        )

    node_ids = set(in_deg) | set(out_deg)
    nodes: list[dict] = []
    for stop_id in sorted(node_ids):
        nodes.append(
            {
                "stop_id": stop_id,
                "in_degree": in_deg.get(stop_id, 0),
                "out_degree": out_deg.get(stop_id, 0),
            }
        )

    stats = {
        "stop_count_raw": len(stops) if stops else len(node_ids),
        "stop_count_filtered": len(node_ids),
        "edge_count_raw": len(edge_samples_raw),
        "edge_count_filtered": len(edge_samples),
    }
    return edges, nodes, stats


def build_edges(gtfs_dir: Path) -> tuple[list[dict], list[dict]]:
    edges, nodes, _ = _build_edges_internal(gtfs_dir)
    return edges, nodes


def _params_hash(params: dict[str, str]) -> str:
    s = json.dumps(params, sort_keys=True, ensure_ascii=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build stop-level graph from GTFS tables")
    parser.add_argument("--gtfs-dir", required=True, help="Directory containing GTFS CSV files")
    parser.add_argument("--out", default="data/graph/latest", help="Output directory")
    parser.add_argument("--gtfs-feed-version", default="", help="GTFS feed version tag (zip file/date)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    edges, nodes, stats = _build_edges_internal(Path(args.gtfs_dir))

    write_csv(
        out_dir / "edges.csv",
        edges,
        ["from_stop_id", "to_stop_id", "scheduled_travel_sec_p50", "trip_count", "route_ids"],
    )
    write_csv(out_dir / "nodes.csv", nodes, ["stop_id", "in_degree", "out_degree"])
    manifest = {
        "data_date": Path(args.gtfs_dir).name,
        "gtfs_feed_version": args.gtfs_feed_version or Path(args.gtfs_dir).name,
        "gtfs_dir": str(Path(args.gtfs_dir)),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "filter_rules": {
            "self_loop_filter": "drop",
            "travel_time_aggregation": "median",
        },
        "build_params": {"self_loop_filter": "drop", "travel_time_aggregation": "median"},
        "build_params_hash": _params_hash({"self_loop_filter": "drop", "travel_time_aggregation": "median"}),
        "stop_count_raw": stats["stop_count_raw"],
        "stop_count_filtered": stats["stop_count_filtered"],
        "edge_count_raw": stats["edge_count_raw"],
        "edge_count_filtered": stats["edge_count_filtered"],
    }
    with (out_dir / "graph_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=True, indent=2)

    print(out_dir / "edges.csv")
    print(out_dir / "nodes.csv")
    print(out_dir / "graph_manifest.json")


if __name__ == "__main__":
    main()
