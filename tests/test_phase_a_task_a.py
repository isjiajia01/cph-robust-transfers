import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_task_a_module():
    fake_bigquery = types.SimpleNamespace(
        Client=object,
        SchemaField=lambda *args, **kwargs: ("SchemaField", args, kwargs),
        Table=object,
        TimePartitioning=object,
    )
    fake_storage = types.SimpleNamespace(Bucket=object, Client=object)
    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_cloud.bigquery = fake_bigquery
    fake_cloud.storage = fake_storage

    with mock.patch.dict(
        sys.modules,
        {
            "google": fake_google,
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
            "google.cloud.storage": fake_storage,
        },
    ):
        return importlib.import_module("src.realtime.task_a_daily_job")


task_a_daily_job = _load_task_a_module()


class PhaseATaskATest(unittest.TestCase):
    def test_gap_diagnostics_sql_contains_phase_a_evidence_fields(self):
        sql = task_a_daily_job._gap_diagnostics_sql("demo-project", "cph_rt")

        for token in (
            "gap_sec",
            "cold_start_proxy_sec",
            "api_error_ratio",
            "dominant_error_code",
            "run_overrun",
            "scheduler_miss_proxy",
            "has_throttle_signal",
            "rule_fired",
            "likely_cause",
        ):
            self.assertIn(token, sql)

    def test_summary_contract_contains_gap_diagnostics_block(self):
        quantiles = [
            {
                "line": "A",
                "p50_delay_sec": "20",
                "p90_delay_sec": "90",
                "p95_delay_sec": "120",
                "n": "25",
            }
        ]
        integrity = {
            "run_count_24h": "480",
            "expected_runs_24h": "481",
            "run_coverage_ratio": "0.9979",
            "expected_interval_sec": "180",
            "first_run_ts": "2026-03-05T19:00:00Z",
            "last_run_ts": "2026-03-06T19:00:00Z",
            "critical_gap_count": "0",
            "warning_gap_count": "0",
            "max_gap_sec": "225",
        }
        gaps = [
            {
                "prev_run_id": "20260306T1757",
                "prev_run_ts": "2026-03-06T17:57:00Z",
                "run_id": "20260306T1801",
                "run_ts": "2026-03-06T18:01:00Z",
                "gap_sec": "240",
            }
        ]
        diag_rows = [
            {
                "run_id": "20260306T1801",
                "gap_sec": 240,
                "likely_cause": "scheduler_miss",
                "rule_fired": "scheduler_miss_proxy",
                "dominant_error_code": "NONE",
            }
        ]

        with tempfile.TemporaryDirectory() as td:
            quantiles_csv = Path(td) / "delay_quantiles_bq.csv"
            integrity_csv = Path(td) / "sampling_integrity_24h.csv"
            quantiles_csv.write_text("line,p50_delay_sec,p90_delay_sec,p95_delay_sec,n\nA,20,90,120,25\n", encoding="utf-8")
            integrity_csv.write_text(
                "run_count_24h,expected_runs_24h,run_coverage_ratio,expected_interval_sec,first_run_ts,last_run_ts,critical_gap_count,warning_gap_count,max_gap_sec\n"
                "480,481,0.9979,180,2026-03-05T19:00:00Z,2026-03-06T19:00:00Z,0,0,225\n",
                encoding="utf-8",
            )

            summary = task_a_daily_job._to_summary_dict(
                quantiles=quantiles,
                integrity=integrity,
                gaps=gaps,
                project_id="demo-project",
                dataset="cph_rt",
                quantiles_path=str(quantiles_csv),
                integrity_path=str(integrity_csv),
            )
            summary["gap_diagnostics"] = {"rows": diag_rows, "row_count": len(diag_rows)}

            self.assertIn("sampling_24h", summary)
            self.assertIn("top_lines_by_p95", summary)
            self.assertIn("gap_diagnostics", summary)
            self.assertEqual(summary["gap_diagnostics"]["row_count"], 1)
            self.assertEqual(summary["gap_diagnostics"]["rows"][0]["likely_cause"], "scheduler_miss")

    def test_uncertainty_block_can_include_risk_model_rows(self):
        quantiles = [
            {"line": "A", "p50_delay_sec": 20, "p90_delay_sec": 90, "p95_delay_sec": 120, "n": 25},
            {"line": "B", "p50_delay_sec": 30, "p90_delay_sec": 100, "p95_delay_sec": 150, "n": 250},
        ]
        with tempfile.TemporaryDirectory() as td:
            risk_csv = Path(td) / "risk_model_mode_level.csv"
            risk_csv.write_text(
                "line,mode,hour_cph,p95_delay_sec,p95_ci_low,p95_ci_high,sample_size_effective,evidence_level,confidence_tag,source_level,uncertainty_note\n"
                "A,train,8,120,80,150,250,high,high,mode_hour,stable\n",
                encoding="utf-8",
            )

            uncertainty = task_a_daily_job._build_uncertainty_block(quantiles, "Europe/Copenhagen", risk_csv)

            self.assertIn("overall_evidence_level", uncertainty)
            self.assertIn("top_lines_by_p95_band", uncertainty)
            self.assertIn("risk_model_quantiles", uncertainty)
            self.assertEqual(uncertainty["risk_model_quantiles"][0]["interval_label"], "bootstrap_ci_95")
            self.assertEqual(uncertainty["risk_model_quantiles"][0]["evidence_level"], "high")


if __name__ == "__main__":
    unittest.main()
