import tempfile
import unittest
from pathlib import Path

from src.app import results_dashboard


class ResultsDashboardTest(unittest.TestCase):
    def test_build_dashboard_contains_core_sections(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "research_dashboard.html"
            html = results_dashboard.build_dashboard_html(repo_root, out_path)

        self.assertIn("CPH Transit Reliability Executive Dashboard", html)
        self.assertIn("Executive View", html)
        self.assertIn("Interactive Line Portfolio", html)
        self.assertIn("Geographic Exposure", html)
        self.assertIn("Decision Support Layer", html)
        self.assertIn('id="line-search"', html)
        self.assertIn('id="map-layer-vulnerable"', html)
        self.assertIn("36,871", html)
        self.assertIn("Re 4516", html)

    def test_render_dashboard_writes_output_file(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "research_dashboard.html"
            written = results_dashboard.render_dashboard(repo_root, out_path)

            self.assertEqual(written, out_path)
            self.assertTrue(out_path.exists())
            self.assertIn("Provenance", out_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
