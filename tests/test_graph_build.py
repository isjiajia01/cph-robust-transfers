import csv
import tempfile
import unittest
from pathlib import Path

from src.graph.build_stop_graph import build_edges


class GraphBuildTest(unittest.TestCase):
    def test_build_edges(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "trips.csv").write_text("route_id,service_id,trip_id\nR1,S1,T1\n", encoding="utf-8")
            (d / "stop_times.csv").write_text(
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                "T1,08:00:00,08:00:00,S1,1\n"
                "T1,08:05:00,08:05:00,S2,2\n",
                encoding="utf-8",
            )
            edges, nodes = build_edges(d)
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["from_stop_id"], "S1")
            self.assertEqual(edges[0]["to_stop_id"], "S2")
            self.assertEqual(edges[0]["scheduled_travel_sec_p50"], 300)
            node_ids = {n["stop_id"] for n in nodes}
            self.assertEqual(node_ids, {"S1", "S2"})


if __name__ == "__main__":
    unittest.main()
