import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.realtime import render_week3_md_from_json


class PhaseDRenderingTest(unittest.TestCase):
    def test_render_week3_md_includes_uncertainty_section(self):
        summary = {
            "generated_at_utc": "2026-03-06T19:00:00Z",
            "source": {"project_id": "demo-project", "dataset": "cph_rt"},
            "sampling_24h": {
                "run_count_24h": 480,
                "expected_runs_24h": 481,
                "coverage_ratio": 0.9979,
                "warning_gap_count": 0,
                "critical_gap_count": 0,
                "max_gap_sec": 225,
                "largest_gaps": [],
            },
            "top_lines_by_p95": [{"line": "A", "p50_delay_sec": 20, "p90_delay_sec": 90, "p95_delay_sec": 120, "n": 25}],
            "uncertainty": {
                "overall_evidence_level": "medium",
                "sample_size_total": 250,
                "risk_model_quantiles": [
                    {
                        "line": "A",
                        "mode": "train",
                        "hour_cph": 8,
                        "point_estimate_sec": 120,
                        "interval_low_sec": 80,
                        "interval_high_sec": 150,
                        "evidence_level": "high",
                        "sample_size": 250,
                    }
                ],
            },
        }
        with tempfile.TemporaryDirectory() as td:
            json_path = Path(td) / "summary.json"
            out_path = Path(td) / "week3_summary.md"
            json_path.write_text(json.dumps(summary), encoding="utf-8")

            argv = [
                "render_week3_md_from_json.py",
                "--input-json",
                str(json_path),
                "--out",
                str(out_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                render_week3_md_from_json.main()

            content = out_path.read_text(encoding="utf-8")
            self.assertIn("Overall evidence level", content)
            self.assertIn("CI=`[80, 150]`", content)


if __name__ == "__main__":
    unittest.main()
