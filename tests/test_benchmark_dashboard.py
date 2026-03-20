import tempfile
import unittest
from pathlib import Path

from src.app import benchmark_dashboard


class BenchmarkDashboardTest(unittest.TestCase):
    def test_build_dashboard_contains_core_sections(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "benchmark_dashboard.html"
            html = benchmark_dashboard.build_benchmark_html(repo_root, out_path)

        self.assertIn("Reliability-Aware Transit Benchmark", html)
        self.assertIn("Rows Evaluated", html)
        self.assertIn("Tradeoff Summary", html)
        self.assertIn("results/benchmark/latest/comparison.csv", html)

    def test_render_dashboard_writes_output_file(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "benchmark_dashboard.html"
            written = benchmark_dashboard.render_dashboard(repo_root, out_path)
            self.assertEqual(written, out_path)
            self.assertTrue(out_path.exists())
            self.assertIn("Benchmark Snapshot", out_path.read_text(encoding="utf-8"))
