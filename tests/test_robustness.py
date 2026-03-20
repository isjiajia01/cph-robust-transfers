import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.graph.build_stop_graph import _build_edges_internal
from src.robustness.simulate_failures import load_undirected_graph, run_simulation
from src.robustness.week2_report import _critical_nodes, _planning_implication, _read_graph_manifest


class RobustnessTest(unittest.TestCase):
    def test_random_is_reproducible(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "edges.csv"
            with p.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["from_stop_id", "to_stop_id"])
                w.writeheader()
                w.writerows(
                    [
                        {"from_stop_id": "A", "to_stop_id": "B"},
                        {"from_stop_id": "B", "to_stop_id": "C"},
                        {"from_stop_id": "C", "to_stop_id": "D"},
                    ]
                )

            g = load_undirected_graph(p)
            r1 = run_simulation(g, "random", [25], repeats=3, seed=7)
            r2 = run_simulation(g, "random", [25], repeats=3, seed=7)
            self.assertEqual(r1, r2)

    def test_build_stop_graph_manifest_fields_exist(self):
        with tempfile.TemporaryDirectory() as td:
            gtfs = Path(td) / "gtfs"
            gtfs.mkdir()
            (gtfs / "trips.csv").write_text("route_id,service_id,trip_id\nR1,S1,T1\n", encoding="utf-8")
            (gtfs / "stop_times.csv").write_text(
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                "T1,08:00:00,08:00:00,S1,1\n"
                "T1,08:05:00,08:05:00,S2,2\n",
                encoding="utf-8",
            )
            (gtfs / "stops.csv").write_text("stop_id,stop_name\nS1,One\nS2,Two\n", encoding="utf-8")

            edges, nodes, stats = _build_edges_internal(gtfs)
            manifest = {
                "data_date": gtfs.name,
                "gtfs_feed_version": gtfs.name,
                "gtfs_dir": str(gtfs),
                "node_count": len(nodes),
                "edge_count": len(edges),
                "filter_rules": {
                    "self_loop_filter": "drop",
                    "travel_time_aggregation": "median",
                },
                "build_params": {"self_loop_filter": "drop", "travel_time_aggregation": "median"},
                "build_params_hash": "placeholder",
                "stop_count_raw": stats["stop_count_raw"],
                "stop_count_filtered": stats["stop_count_filtered"],
                "edge_count_raw": stats["edge_count_raw"],
                "edge_count_filtered": stats["edge_count_filtered"],
            }

            self.assertEqual(manifest["node_count"], 2)
            self.assertEqual(manifest["edge_count"], 1)
            self.assertIn("filter_rules", manifest)
            self.assertEqual(manifest["stop_count_filtered"], 2)

    def test_critical_nodes_include_planning_implication(self):
        g = {
            "A": {"B", "C"},
            "B": {"A", "C"},
            "C": {"A", "B", "D"},
            "D": {"C"},
        }
        nodes = [
            {"stop_id": "A", "in_degree": "1", "out_degree": "1"},
            {"stop_id": "B", "in_degree": "1", "out_degree": "1"},
            {"stop_id": "C", "in_degree": "2", "out_degree": "1"},
            {"stop_id": "D", "in_degree": "1", "out_degree": "0"},
        ]

        rows = _critical_nodes(g, nodes, top_n=4, k_out=2, betweenness_sources=4, seed=42)

        self.assertEqual(len(rows), 2)
        self.assertIn("planning_implication", rows[0])
        self.assertTrue(rows[0]["planning_implication"])

    def test_planning_implication_bands(self):
        high = _planning_implication(3, 0.01, 0.25)
        bridge = _planning_implication(3, 0.05, 0.1)
        hub = _planning_implication(10, 0.005, 0.05)
        local = _planning_implication(2, 0.001, 0.01)

        self.assertIn("single-point failure", high)
        self.assertIn("transfer bridge", bridge)
        self.assertIn("High-connectivity hub", hub)
        self.assertIn("Localized vulnerability", local)

    def test_read_graph_manifest_from_edges_dir(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            edges = base / "edges.csv"
            manifest = base / "graph_manifest.json"
            edges.write_text("from_stop_id,to_stop_id\nA,B\n", encoding="utf-8")
            manifest.write_text(json.dumps({"node_count": 2, "edge_count": 1}), encoding="utf-8")

            loaded = _read_graph_manifest(edges)

            self.assertEqual(loaded["node_count"], 2)


if __name__ == "__main__":
    unittest.main()
