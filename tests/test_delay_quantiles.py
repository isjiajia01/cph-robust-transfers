import tempfile
import unittest
from pathlib import Path

from src.realtime.delay_quantiles import compute_quantiles


class DelayQuantilesTest(unittest.TestCase):
    def test_quantiles(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "departures.csv"
            p.write_text(
                "obs_ts_utc,run_id,station_gtfs_id,api_station_id,line,mode,direction,planned_dep_ts,realtime_dep_ts,delay_sec,journey_ref\n"
                "2026-03-02T09:59:00Z,run1,,123,A,bus,Center,2026-03-02T10:00:00,2026-03-02T10:01:00,,x\n"
                "2026-03-02T09:59:00Z,run1,,123,A,bus,Center,2026-03-02T10:00:00,2026-03-02T10:03:00,,y\n"
                "2026-03-02T09:59:00Z,run1,,123,A,bus,Center,2026-03-02T10:00:00,2026-03-02T10:02:00,,z\n",
                encoding="utf-8",
            )
            rows = compute_quantiles(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["line"], "A")
            self.assertEqual(rows[0]["p50_delay_sec"], 120)


if __name__ == "__main__":
    unittest.main()
