import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.realtime import collector


class _FakeJob:
    def result(self):
        return None


class _FakeClient:
    def __init__(self, project: str):
        self.project = project
        self.tables = set()
        self.loaded = []

    def get_table(self, table_id: str):
        if table_id not in self.tables:
            raise RuntimeError("missing")
        return table_id

    def create_table(self, table):
        self.tables.add(table.table_id)
        return table

    def load_table_from_file(self, file_obj, table_id: str, job_config=None):
        self.loaded.append((Path(file_obj.name).name, table_id, job_config))
        return _FakeJob()


class _FakeBigQueryModule:
    class SchemaField:
        def __init__(self, name, field_type):
            self.name = name
            self.field_type = field_type

    class Table:
        def __init__(self, table_id, schema=None):
            self.table_id = table_id
            self.schema = schema

    class LoadJobConfig:
        def __init__(self, schema=None, source_format=None, skip_leading_rows=None, write_disposition=None):
            self.schema = schema
            self.source_format = source_format
            self.skip_leading_rows = skip_leading_rows
            self.write_disposition = write_disposition
            self.allow_jagged_rows = False

    class SourceFormat:
        CSV = "CSV"

    class WriteDisposition:
        WRITE_APPEND = "WRITE_APPEND"

    def __init__(self):
        self.client = _FakeClient("test-project")

    def Client(self, project: str):
        self.client.project = project
        return self.client


class RealtimeCollectorTest(unittest.TestCase):
    def test_finalize_observation_rows_adds_job_end_and_run_status(self):
        rows = [
            {
                "run_id": "20260306T1827",
                "trigger_id": "20260306T1827",
                "scheduled_ts_utc": "2026-03-06T18:27:00Z",
                "job_start_ts_utc": "2026-03-06T18:27:02Z",
                "request_ts": "2026-03-06T18:27:05Z",
                "endpoint": "multiDepartureBoard",
            }
        ]

        finalized = collector._finalize_observation_rows(
            rows,
            job_end_ts="2026-03-06T18:27:40Z",
            run_status="partial",
        )

        self.assertEqual(finalized[0]["job_end_ts_utc"], "2026-03-06T18:27:40Z")
        self.assertEqual(finalized[0]["run_status"], "partial")
        self.assertNotIn("job_end_ts_utc", rows[0])
        self.assertNotIn("run_status", rows[0])

    def test_build_run_metrics_row_tracks_phase_a_fields(self):
        row = collector._build_run_metrics_row(
            run_id="20260306T1827",
            trigger_id="exec-123",
            scheduled_ts="2026-03-06T18:27:00Z",
            job_start_ts="2026-03-06T18:27:02Z",
            job_end_ts="2026-03-06T18:27:40Z",
            duration_sec=38,
            schedule_interval_sec=180,
            station_count=12,
            board_request_count=3,
            journey_request_count=8,
            success_count=10,
            error_count=1,
            status_2xx_count=10,
            status_4xx_count=1,
            status_5xx_count=0,
            run_status="partial",
            collector_version="abc1234",
            sampling_target_version="def5678",
        )

        self.assertEqual(row["duration_sec"], 38)
        self.assertEqual(row["status_2xx_count"], 10)
        self.assertEqual(row["status_4xx_count"], 1)
        self.assertEqual(row["status_5xx_count"], 0)
        self.assertEqual(row["run_status"], "partial")
        self.assertEqual(row["collector_version"], "abc1234")
        self.assertEqual(row["sampling_target_version"], "def5678")

    def test_csv_has_data(self):
        with tempfile.TemporaryDirectory() as td:
            empty_csv = Path(td) / "empty.csv"
            empty_csv.write_text("col\n", encoding="utf-8")
            full_csv = Path(td) / "full.csv"
            full_csv.write_text("col\nvalue\n", encoding="utf-8")
            self.assertFalse(collector._csv_has_data(empty_csv))
            self.assertTrue(collector._csv_has_data(full_csv))

    def test_load_structured_dir_to_bq_skips_header_only_files(self):
        fake_bq = _FakeBigQueryModule()
        fake_schemas = {
            "departures": [fake_bq.SchemaField("obs_ts_utc", "STRING")],
            "journey_stops": [fake_bq.SchemaField("obs_ts_utc", "STRING")],
            "observations": [fake_bq.SchemaField("run_id", "STRING")],
            "api_errors": [fake_bq.SchemaField("obs_ts_utc", "STRING")],
            "run_metrics": [fake_bq.SchemaField("run_id", "STRING")],
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "departures.csv").write_text("obs_ts_utc\n2026-03-06T18:06:00Z\n", encoding="utf-8")
            (root / "journey_stops.csv").write_text("obs_ts_utc\n", encoding="utf-8")
            (root / "observations.csv").write_text("run_id\nrun1\n", encoding="utf-8")
            (root / "api_errors.csv").write_text("obs_ts_utc\n", encoding="utf-8")
            (root / "run_metrics.csv").write_text("run_id\nrun1\n", encoding="utf-8")

            with mock.patch.object(collector, "_bigquery_table_schemas", return_value=(fake_bq, fake_schemas)):
                collector._load_structured_dir_to_bq(root, "cph_rt", "test-project")

        loaded_files = [name for name, _, _ in fake_bq.client.loaded]
        self.assertEqual(loaded_files, ["departures.csv", "observations.csv", "run_metrics.csv"])
        self.assertIn("test-project.cph_rt.departures", fake_bq.client.tables)
        self.assertIn("test-project.cph_rt.run_metrics", fake_bq.client.tables)


if __name__ == "__main__":
    unittest.main()
