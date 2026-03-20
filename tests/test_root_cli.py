import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import cli as root_cli


class RootCliTest(unittest.TestCase):
    def test_root_cli_parser_accepts_top_level_commands(self):
        parser = root_cli.build_parser()
        self.assertEqual(parser.parse_args(["ingest"]).command, "ingest")
        self.assertEqual(parser.parse_args(["benchmark"]).command, "benchmark")
        self.assertEqual(parser.parse_args(["accessibility"]).command, "accessibility")

    def test_root_cli_dispatches_report_with_passthrough_args(self):
        with mock.patch("src.app.results_dashboard.main", return_value=0) as dashboard_main:
            rc = root_cli.main(["report", "--out", "docs/research_dashboard.html"])

        self.assertEqual(rc, 0)
        dashboard_main.assert_called_once_with(["--out", "docs/research_dashboard.html"])

    def test_benchmark_init_creates_manifest(self):
        tmp_dir = Path(tempfile.mkdtemp(prefix="cph-rt-bench-"))
        try:
            out_path = tmp_dir / "manifest.md"
            rc = root_cli.main(["benchmark", "init", "--out", str(out_path)])
            self.assertEqual(rc, 0)
            self.assertTrue(out_path.exists())
        finally:
            shutil.rmtree(tmp_dir)

    def test_root_cli_accessibility_dispatches_serve_subcommand(self):
        with mock.patch("src.accessibility.server.main", return_value=0) as server_main:
            rc = root_cli.main(["accessibility", "--host", "127.0.0.1", "--port", "8765"])

        self.assertEqual(rc, 0)
        server_main.assert_called_once_with(["serve", "--host", "127.0.0.1", "--port", "8765"])
