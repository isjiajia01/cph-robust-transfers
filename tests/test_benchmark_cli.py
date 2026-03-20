import shutil
import tempfile
import unittest
from pathlib import Path

from src.benchmark import cli as benchmark_cli


class BenchmarkCliTest(unittest.TestCase):
    def test_compare_and_summarize_generate_outputs(self):
        repo_root = Path(__file__).resolve().parents[1]
        tmp_dir = Path(tempfile.mkdtemp(prefix="cph-rt-benchmark-"))
        try:
            candidates = tmp_dir / "candidates.csv"
            comparison = tmp_dir / "comparison.csv"
            summary = tmp_dir / "summary.md"
            rc_generate = benchmark_cli.main(
                [
                    "generate-candidates",
                    "--departures",
                    str(repo_root / "data" / "analysis" / "departures_recent_7d.csv"),
                    "--out",
                    str(candidates),
                ]
            )
            self.assertEqual(rc_generate, 0)
            self.assertTrue(candidates.exists())

            rc_compare = benchmark_cli.main(
                [
                    "compare",
                    "--departures",
                    str(repo_root / "data" / "analysis" / "departures_recent_7d.csv"),
                    "--candidates",
                    str(candidates),
                    "--out",
                    str(comparison),
                ]
            )
            self.assertEqual(rc_compare, 0)
            self.assertTrue(comparison.exists())

            rc_summary = benchmark_cli.main(
                [
                    "summarize",
                    "--input",
                    str(comparison),
                    "--out",
                    str(summary),
                ]
            )
            self.assertEqual(rc_summary, 0)
            self.assertTrue(summary.exists())
        finally:
            shutil.rmtree(tmp_dir)
