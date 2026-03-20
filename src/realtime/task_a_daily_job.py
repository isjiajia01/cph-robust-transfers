from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from google.cloud import storage

from src.realtime.update_week3_summary import _to_summary_dict


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _run_query(client: bigquery.Client, sql: str) -> tuple[list[dict], int]:
    job = client.query(sql)
    rows = job.result()
    out: list[dict] = []
    for row in rows:
        out.append({k: row[k] for k in row.keys()})
    return (out, int(job.total_bytes_processed or 0))


def _quantiles_sql(project_id: str, dataset: str) -> str:
    table_ref = f"`{project_id}.{dataset}.departures`"
    return f"""
WITH cleaned AS (
  SELECT
    line,
    SAFE.TIMESTAMP(realtime_dep_ts) AS realtime_ts,
    SAFE.TIMESTAMP(planned_dep_ts) AS planned_ts
  FROM {table_ref}
  WHERE SAFE.TIMESTAMP(obs_ts_utc) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
)
SELECT
  line,
  APPROX_QUANTILES(TIMESTAMP_DIFF(realtime_ts, planned_ts, SECOND), 100)[OFFSET(50)] AS p50_delay_sec,
  APPROX_QUANTILES(TIMESTAMP_DIFF(realtime_ts, planned_ts, SECOND), 100)[OFFSET(90)] AS p90_delay_sec,
  APPROX_QUANTILES(TIMESTAMP_DIFF(realtime_ts, planned_ts, SECOND), 100)[OFFSET(95)] AS p95_delay_sec,
  COUNT(*) AS n
FROM cleaned
WHERE realtime_ts IS NOT NULL AND planned_ts IS NOT NULL
GROUP BY line
ORDER BY p95_delay_sec DESC
"""


def _integrity_summary_sql(project_id: str, dataset: str, interval_sec: int) -> str:
    table_ref = f"`{project_id}.{dataset}.observations`"
    return f"""
WITH runs AS (
  SELECT
    run_id,
    SAFE.TIMESTAMP(MIN(request_ts)) AS run_ts
  FROM {table_ref}
  GROUP BY run_id
),
windowed AS (
  SELECT run_id, run_ts
  FROM runs
  WHERE run_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    AND run_ts IS NOT NULL
),
ordered AS (
  SELECT
    run_id,
    run_ts,
    LAG(run_ts) OVER (ORDER BY run_ts) AS prev_run_ts
  FROM windowed
),
gaps AS (
  SELECT
    run_id,
    run_ts,
    prev_run_ts,
    TIMESTAMP_DIFF(run_ts, prev_run_ts, SECOND) AS gap_sec
  FROM ordered
  WHERE prev_run_ts IS NOT NULL
),
stats AS (
  SELECT
    COUNT(*) AS run_count_24h,
    MIN(run_ts) AS first_run_ts,
    MAX(run_ts) AS last_run_ts,
    CAST({interval_sec} AS INT64) AS expected_interval_sec,
    CAST(FLOOR(86400.0 / CAST({interval_sec} AS FLOAT64)) + 1 AS INT64) AS expected_runs_24h
  FROM windowed
),
gap_stats AS (
  SELECT
    COUNTIF(gap_sec > CAST({interval_sec} AS INT64) * 2) AS critical_gap_count,
    COUNTIF(gap_sec > CAST({interval_sec} AS INT64) * 1.5) AS warning_gap_count,
    MAX(gap_sec) AS max_gap_sec
  FROM gaps
)
SELECT
  run_count_24h,
  expected_runs_24h,
  SAFE_DIVIDE(run_count_24h, expected_runs_24h) AS run_coverage_ratio,
  expected_interval_sec,
  first_run_ts,
  last_run_ts,
  COALESCE(critical_gap_count, 0) AS critical_gap_count,
  COALESCE(warning_gap_count, 0) AS warning_gap_count,
  COALESCE(max_gap_sec, 0) AS max_gap_sec
FROM stats CROSS JOIN gap_stats
"""


def _integrity_gaps_sql(project_id: str, dataset: str, interval_sec: int) -> str:
    table_ref = f"`{project_id}.{dataset}.observations`"
    return f"""
WITH runs AS (
  SELECT
    run_id,
    SAFE.TIMESTAMP(MIN(request_ts)) AS run_ts
  FROM {table_ref}
  GROUP BY run_id
),
windowed AS (
  SELECT run_id, run_ts
  FROM runs
  WHERE run_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    AND run_ts IS NOT NULL
),
ordered AS (
  SELECT
    run_id,
    run_ts,
    LAG(run_id) OVER (ORDER BY run_ts) AS prev_run_id,
    LAG(run_ts) OVER (ORDER BY run_ts) AS prev_run_ts
  FROM windowed
)
SELECT
  prev_run_id,
  prev_run_ts,
  run_id,
  run_ts,
  TIMESTAMP_DIFF(run_ts, prev_run_ts, SECOND) AS gap_sec
FROM ordered
WHERE prev_run_ts IS NOT NULL
  AND TIMESTAMP_DIFF(run_ts, prev_run_ts, SECOND) > CAST({interval_sec} AS INT64) * 1.5
ORDER BY gap_sec DESC, run_ts DESC
"""


def _gap_diagnostics_sql(project_id: str, dataset: str) -> str:
    run_table = f"`{project_id}.{dataset}.run_metrics`"
    err_table = f"`{project_id}.{dataset}.api_errors`"
    return f"""
WITH ordered AS (
  SELECT
    r.*,
    SAFE.TIMESTAMP(r.scheduled_ts_utc) AS scheduled_ts,
    SAFE.TIMESTAMP(r.job_start_ts_utc) AS job_start_ts,
    LAG(SAFE.TIMESTAMP(r.scheduled_ts_utc)) OVER (ORDER BY SAFE.TIMESTAMP(r.scheduled_ts_utc)) AS prev_scheduled_ts
  FROM {run_table} r
),
err AS (
  SELECT
    run_id,
    COUNT(*) AS error_rows,
    COUNTIF(http_code = 429 OR error_code = 'API_TOO_MANY_REQUESTS' OR error_code = 'API_QUOTA') AS throttled_rows,
    ARRAY_AGG(error_code IGNORE NULLS ORDER BY error_code LIMIT 1)[SAFE_OFFSET(0)] AS dominant_error_code
  FROM {err_table}
  GROUP BY run_id
)
SELECT
  x.run_id,
  x.trigger_id,
  x.scheduled_ts_utc,
  x.job_start_ts_utc,
  x.job_end_ts_utc,
  x.gap_sec,
  x.cold_start_proxy_sec,
  x.api_error_ratio,
  x.dominant_error_code,
  x.run_overrun,
  x.scheduler_miss_proxy,
  x.has_throttle_signal,
  x.rule_fired,
  x.likely_cause
FROM (
  SELECT
    o.run_id,
    o.trigger_id,
    o.scheduled_ts_utc,
    o.job_start_ts_utc,
    o.job_end_ts_utc,
    TIMESTAMP_DIFF(o.scheduled_ts, o.prev_scheduled_ts, SECOND) AS gap_sec,
    TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND) AS cold_start_proxy_sec,
    SAFE_DIVIDE(COALESCE(e.error_rows, 0), NULLIF(o.board_request_count + o.journey_request_count, 0)) AS api_error_ratio,
    COALESCE(e.dominant_error_code, 'NONE') AS dominant_error_code,
    o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64) AS run_overrun,
    ABS(TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND)) > 120 AS scheduler_miss_proxy,
    COALESCE(e.throttled_rows, 0) > 0 AS has_throttle_signal,
    CASE
      WHEN o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64) AND COALESCE(e.throttled_rows, 0) > 0
        THEN 'duration_overrun && throttle_signal'
      WHEN ABS(TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND)) > 120
        THEN 'scheduler_miss_proxy'
      WHEN o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64)
        THEN 'duration_overrun'
      WHEN COALESCE(e.throttled_rows, 0) > 0
        THEN 'throttle_signal'
      ELSE 'fallback_unknown'
    END AS rule_fired,
    CASE
      WHEN ABS(TIMESTAMP_DIFF(o.job_start_ts, o.scheduled_ts, SECOND)) > 120 THEN 'scheduler_miss'
      WHEN o.duration_sec > CAST(o.schedule_interval_sec * 0.9 AS INT64) THEN 'run_overrun'
      WHEN COALESCE(e.throttled_rows, 0) > 0 THEN 'api_throttle'
      ELSE 'network_or_unknown'
    END AS likely_cause
  FROM ordered o
  LEFT JOIN err e USING (run_id)
) x
WHERE gap_sec IS NOT NULL
ORDER BY gap_sec DESC
LIMIT 200
"""


def _daily_summary_schema() -> list[bigquery.SchemaField]:
    return [
        bigquery.SchemaField("dt_local", "DATE"),
        bigquery.SchemaField("generated_at_utc", "TIMESTAMP"),
        bigquery.SchemaField("coverage_ratio", "FLOAT"),
        bigquery.SchemaField("critical_gap_count", "INT64"),
        bigquery.SchemaField("max_gap_sec", "INT64"),
        bigquery.SchemaField("error_429_ratio", "FLOAT"),
        bigquery.SchemaField("duplicate_ratio", "FLOAT"),
        bigquery.SchemaField("sample_size_total", "INT64"),
        bigquery.SchemaField("bytes_scanned_estimate", "INT64"),
        bigquery.SchemaField("collector_version", "STRING"),
        bigquery.SchemaField("sampling_target_version", "STRING"),
    ]


def _ensure_base_tables(client: bigquery.Client, project_id: str, dataset: str) -> None:
    schemas = {
        f"{project_id}.{dataset}.api_errors": [
            bigquery.SchemaField("obs_ts_utc", "STRING"),
            bigquery.SchemaField("ingest_ts_utc", "STRING"),
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("trigger_id", "STRING"),
            bigquery.SchemaField("endpoint", "STRING"),
            bigquery.SchemaField("http_code", "INT64"),
            bigquery.SchemaField("error_code", "STRING"),
            bigquery.SchemaField("message", "STRING"),
            bigquery.SchemaField("station_id", "STRING"),
            bigquery.SchemaField("journey_ref", "STRING"),
            bigquery.SchemaField("latency_ms", "INT64"),
            bigquery.SchemaField("retry_count", "INT64"),
            bigquery.SchemaField("request_id", "STRING"),
            bigquery.SchemaField("is_retry_final", "BOOL"),
        ],
        f"{project_id}.{dataset}.run_metrics": [
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("trigger_id", "STRING"),
            bigquery.SchemaField("scheduled_ts_utc", "STRING"),
            bigquery.SchemaField("job_start_ts_utc", "STRING"),
            bigquery.SchemaField("job_end_ts_utc", "STRING"),
            bigquery.SchemaField("duration_sec", "INT64"),
            bigquery.SchemaField("schedule_interval_sec", "INT64"),
            bigquery.SchemaField("station_count", "INT64"),
            bigquery.SchemaField("board_request_count", "INT64"),
            bigquery.SchemaField("journey_request_count", "INT64"),
            bigquery.SchemaField("success_count", "INT64"),
            bigquery.SchemaField("error_count", "INT64"),
            bigquery.SchemaField("status_2xx_count", "INT64"),
            bigquery.SchemaField("status_4xx_count", "INT64"),
            bigquery.SchemaField("status_5xx_count", "INT64"),
            bigquery.SchemaField("run_status", "STRING"),
            bigquery.SchemaField("collector_version", "STRING"),
            bigquery.SchemaField("sampling_target_version", "STRING"),
        ],
    }
    for table_id, schema in schemas.items():
        try:
            client.get_table(table_id)
        except Exception:
            client.create_table(bigquery.Table(table_id, schema=schema))


def _ensure_daily_summary_table(client: bigquery.Client, project_id: str, dataset: str) -> str:
    table_id = f"{project_id}.{dataset}.daily_summary"
    table = bigquery.Table(table_id, schema=_daily_summary_schema())
    table.time_partitioning = bigquery.TimePartitioning(field="generated_at_utc")
    try:
        client.get_table(table_id)
    except Exception:
        client.create_table(table)
    return table_id


def _recent_run_versions(client: bigquery.Client, project_id: str, dataset: str) -> tuple[str, str]:
    sql = f"""
SELECT
  ARRAY_AGG(collector_version IGNORE NULLS ORDER BY SAFE.TIMESTAMP(job_end_ts_utc) DESC LIMIT 1)[SAFE_OFFSET(0)] AS collector_version,
  ARRAY_AGG(sampling_target_version IGNORE NULLS ORDER BY SAFE.TIMESTAMP(job_end_ts_utc) DESC LIMIT 1)[SAFE_OFFSET(0)] AS sampling_target_version
FROM `{project_id}.{dataset}.run_metrics`
"""
    rows, _ = _run_query(client, sql)
    if not rows:
        return ("unknown", "unknown")
    row = rows[0]
    return (str(row.get("collector_version") or "unknown"), str(row.get("sampling_target_version") or "unknown"))


def _error_429_ratio(client: bigquery.Client, project_id: str, dataset: str) -> float:
    sql = f"""
SELECT
  SAFE_DIVIDE(
    COUNTIF(http_code = 429 OR error_code = 'API_TOO_MANY_REQUESTS' OR error_code = 'API_QUOTA'),
    NULLIF(COUNT(*), 0)
  ) AS ratio
FROM `{project_id}.{dataset}.api_errors`
WHERE SAFE.TIMESTAMP(obs_ts_utc) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
"""
    rows, _ = _run_query(client, sql)
    if not rows:
        return 0.0
    return float(rows[0].get("ratio") or 0.0)


def _duplicate_ratio(client: bigquery.Client, project_id: str, dataset: str) -> float:
    sql = f"""
WITH scoped AS (
  SELECT run_id, api_station_id, journey_ref, planned_dep_ts
  FROM `{project_id}.{dataset}.departures`
  WHERE SAFE.TIMESTAMP(obs_ts_utc) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
),
agg AS (
  SELECT COUNT(*) AS total_rows, COUNT(DISTINCT TO_JSON_STRING(STRUCT(run_id, api_station_id, journey_ref, planned_dep_ts))) AS unique_rows
  FROM scoped
)
SELECT SAFE_DIVIDE(total_rows - unique_rows, NULLIF(total_rows, 0)) AS duplicate_ratio
FROM agg
"""
    rows, _ = _run_query(client, sql)
    if not rows:
        return 0.0
    return float(rows[0].get("duplicate_ratio") or 0.0)


def _upload(local_path: Path, bucket: storage.Bucket, object_name: str) -> None:
    bucket.blob(object_name).upload_from_filename(str(local_path))


def _evidence_level_from_n(n: int) -> str:
    if n < 50:
        return "low"
    if n < 200:
        return "medium"
    return "high"


def _build_uncertainty_block(
    quantiles: list[dict],
    report_timezone: str,
    risk_model_csv: Path | None,
) -> dict:
    top_rows = sorted(quantiles, key=lambda r: int(r.get("p95_delay_sec") or 0), reverse=True)[:5]
    top_line_rows = []
    for row in top_rows:
        n = int(row.get("n") or 0)
        top_line_rows.append(
            {
                "line": row.get("line", ""),
                "point_estimate_sec": int(row.get("p95_delay_sec") or 0),
                "interval_low_sec": int(row.get("p90_delay_sec") or 0),
                "interval_high_sec": int(row.get("p95_delay_sec") or 0),
                "interval_label": "p90_to_p95_delay_band",
                "sample_size": n,
                "evidence_level": _evidence_level_from_n(n),
            }
        )

    risk_rows: list[dict] = []
    if risk_model_csv and risk_model_csv.exists():
        with risk_model_csv.open("r", encoding="utf-8", newline="") as f:
            risk_rows = list(csv.DictReader(f))
    top_risk_rows = sorted(risk_rows, key=lambda r: int(r.get("p95_delay_sec") or 0), reverse=True)[:5]
    risk_quantiles = []
    for row in top_risk_rows:
        risk_quantiles.append(
            {
                "line": row.get("line", ""),
                "mode": row.get("mode", ""),
                "hour_cph": row.get("hour_cph", ""),
                "point_estimate_sec": int(row.get("p95_delay_sec") or 0),
                "interval_low_sec": int(row.get("p95_ci_low") or 0),
                "interval_high_sec": int(row.get("p95_ci_high") or 0),
                "interval_label": "bootstrap_ci_95",
                "sample_size": int(row.get("sample_size_effective") or 0),
                "evidence_level": row.get("evidence_level", "low"),
                "confidence_tag": row.get("confidence_tag", "low"),
                "source_level": row.get("source_level", "unknown"),
                "uncertainty_note": row.get("uncertainty_note", ""),
            }
        )

    overall_sample_size = sum(int(r.get("n") or 0) for r in quantiles)
    overall_evidence = _evidence_level_from_n(overall_sample_size // max(1, len(quantiles))) if quantiles else "low"
    return {
        "report_timezone": report_timezone,
        "overall_evidence_level": overall_evidence,
        "sample_size_total": overall_sample_size,
        "top_lines_by_p95_band": top_line_rows,
        "risk_model_quantiles": risk_quantiles,
    }


def main() -> None:
    project_id = os.getenv("PROJECT_ID", "").strip()
    dataset = os.getenv("BQ_DATASET", "cph_rt").strip()
    report_bucket_name = os.getenv("REPORT_BUCKET", "").strip()
    bq_location = os.getenv("BQ_LOCATION", "europe-north1").strip()
    interval_sec = int(os.getenv("INTERVAL_SEC", "180").strip())
    report_tz = os.getenv("REPORT_TIMEZONE", "Europe/Copenhagen").strip()
    if not project_id:
        raise SystemExit("Missing PROJECT_ID env")
    if not report_bucket_name:
        raise SystemExit("Missing REPORT_BUCKET env")

    client = bigquery.Client(project=project_id, location=bq_location)
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(report_bucket_name)
    _ensure_base_tables(client, project_id, dataset)

    quantiles, bq1 = _run_query(client, _quantiles_sql(project_id, dataset))
    integrity_rows, bq2 = _run_query(client, _integrity_summary_sql(project_id, dataset, interval_sec))
    gap_rows, bq3 = _run_query(client, _integrity_gaps_sql(project_id, dataset, interval_sec))
    diag_rows, bq4 = _run_query(client, _gap_diagnostics_sql(project_id, dataset))
    integrity = integrity_rows[0] if integrity_rows else {}
    bytes_scanned_estimate = bq1 + bq2 + bq3 + bq4

    now_utc = datetime.now(timezone.utc)
    dt_local = now_utc.astimezone(ZoneInfo(report_tz)).date().isoformat()
    out_dir = Path("/tmp") / "week3_reports" / f"dt={dt_local}"
    out_dir.mkdir(parents=True, exist_ok=True)

    quantiles_csv = out_dir / "delay_quantiles_bq.csv"
    integrity_csv = out_dir / "sampling_integrity_24h.csv"
    gaps_csv = out_dir / "sampling_gaps_24h.csv"
    summary_json = out_dir / "summary.json"
    summary_md = out_dir / "summary.md"

    _write_csv(
        quantiles_csv,
        quantiles,
        ["line", "p50_delay_sec", "p90_delay_sec", "p95_delay_sec", "n"],
    )
    _write_csv(
        integrity_csv,
        [integrity],
        [
            "run_count_24h",
            "expected_runs_24h",
            "run_coverage_ratio",
            "expected_interval_sec",
            "first_run_ts",
            "last_run_ts",
            "critical_gap_count",
            "warning_gap_count",
            "max_gap_sec",
        ],
    )
    _write_csv(gaps_csv, gap_rows, ["prev_run_id", "prev_run_ts", "run_id", "run_ts", "gap_sec"])

    summary = _to_summary_dict(
        quantiles=quantiles,
        integrity={k: ("" if v is None else str(v)) for k, v in integrity.items()},
        gaps=[{k: ("" if v is None else str(v)) for k, v in r.items()} for r in gap_rows],
        project_id=project_id,
        dataset=dataset,
        quantiles_path=str(quantiles_csv),
        integrity_path=str(integrity_csv),
    )
    summary["gap_diagnostics"] = {
        "rows": diag_rows,
        "row_count": len(diag_rows),
    }
    summary["cost_guardrails"] = {
        "bytes_scanned_estimate": bytes_scanned_estimate,
        "quantiles_window_days": 7,
        "integrity_window_hours": 24,
    }
    summary["dedup_metrics"] = {"duplicate_ratio": _duplicate_ratio(client, project_id, dataset)}
    summary["sampling_24h"]["error_429_ratio"] = _error_429_ratio(client, project_id, dataset)
    summary["report_timezone"] = report_tz
    summary["dt_local"] = dt_local
    risk_model_csv = Path(os.getenv("RISK_MODEL_CSV", "data/analysis/risk_model_mode_level.csv").strip())
    summary["uncertainty"] = _build_uncertainty_block(quantiles, report_tz, risk_model_csv)
    summary["evidence_level"] = summary["uncertainty"]["overall_evidence_level"]
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=True, indent=2)

    top_lines = summary.get("top_lines_by_p95", [])[:10]
    with summary_md.open("w", encoding="utf-8") as f:
        f.write("# Week3 Summary\n\n")
        f.write(f"- Generated (UTC): `{summary.get('generated_at_utc', '')}`\n")
        f.write(f"- Source: BigQuery `{project_id}.{dataset}`\n")
        f.write("\n## 24h Sampling Integrity\n")
        sampling = summary.get("sampling_24h", {})
        f.write(
            f"- Runs observed: `{sampling.get('run_count_24h', 0)}` / expected "
            f"`{sampling.get('expected_runs_24h', 0)}` (coverage `{float(sampling.get('coverage_ratio', 0.0)):.2%}`)\n"
        )
        f.write(f"- Gap warnings (>1.5x interval): `{sampling.get('warning_gap_count', 0)}`\n")
        f.write(f"- Critical gaps (>2x interval): `{sampling.get('critical_gap_count', 0)}`\n")
        f.write(f"- Maximum gap: `{sampling.get('max_gap_sec', 0)}` seconds\n")
        gap_diag = summary.get("gap_diagnostics", {})
        f.write(f"- Gap diagnostics rows: `{gap_diag.get('row_count', 0)}`\n")
        if sampling.get("first_run_ts"):
            f.write(f"- First run in window: `{sampling.get('first_run_ts')}`\n")
        if sampling.get("last_run_ts"):
            f.write(f"- Last run in window: `{sampling.get('last_run_ts')}`\n")
        diag_rows = gap_diag.get("rows", [])[:5]
        if diag_rows:
            f.write("\n## Gap Diagnostics (Top 5)\n")
            for row in diag_rows:
                f.write(
                    f"- run `{row.get('run_id')}`: gap={row.get('gap_sec')}s, "
                    f"cause={row.get('likely_cause')}, rule=`{row.get('rule_fired')}`, "
                    f"dominant_error=`{row.get('dominant_error_code')}`\n"
                )
        uncertainty = summary.get("uncertainty", {})
        f.write("\n## Uncertainty\n")
        f.write(f"- Overall evidence level: `{uncertainty.get('overall_evidence_level', 'low')}`\n")
        f.write(f"- Sample size total: `{uncertainty.get('sample_size_total', 0)}`\n")
        for row in (uncertainty.get("risk_model_quantiles") or [])[:5]:
            f.write(
                f"- {row.get('line')} ({row.get('mode')}, hour {row.get('hour_cph')}): "
                f"P95=`{row.get('point_estimate_sec')}`s, "
                f"CI=`[{row.get('interval_low_sec')}, {row.get('interval_high_sec')}]`, "
                f"evidence=`{row.get('evidence_level')}`, n=`{row.get('sample_size')}`\n"
            )
        f.write("\n## Top Lines by P95 Delay\n")
        for row in top_lines:
            f.write(
                f"- {row.get('line')}: P50={row.get('p50_delay_sec')}s, "
                f"P90={row.get('p90_delay_sec')}s, P95={row.get('p95_delay_sec')}s, n={row.get('n')}\n"
            )

    dt_prefix = f"reports/week3/dt={dt_local}"
    latest_prefix = "reports/week3/latest"
    for fname in ("summary.json", "summary.md", "delay_quantiles_bq.csv", "sampling_integrity_24h.csv", "sampling_gaps_24h.csv"):
        _upload(out_dir / fname, bucket, f"{dt_prefix}/{fname}")
        _upload(out_dir / fname, bucket, f"{latest_prefix}/{fname}")

    daily_table = _ensure_daily_summary_table(client, project_id, dataset)
    collector_version, sampling_target_version = _recent_run_versions(client, project_id, dataset)
    sample_size_total = int(sum(int(r.get("n") or 0) for r in quantiles))
    row = {
        "dt_local": dt_local,
        "generated_at_utc": now_utc.isoformat(),
        "coverage_ratio": float(integrity.get("run_coverage_ratio") or 0.0),
        "critical_gap_count": int(integrity.get("critical_gap_count") or 0),
        "max_gap_sec": int(integrity.get("max_gap_sec") or 0),
        "error_429_ratio": float(summary["sampling_24h"]["error_429_ratio"] or 0.0),
        "duplicate_ratio": float(summary["dedup_metrics"]["duplicate_ratio"] or 0.0),
        "sample_size_total": sample_size_total,
        "bytes_scanned_estimate": int(bytes_scanned_estimate),
        "collector_version": collector_version,
        "sampling_target_version": sampling_target_version,
    }
    errors = client.insert_rows_json(daily_table, [row])
    if errors:
        raise RuntimeError(f"daily_summary insert failed: {errors}")

    print(f"uploaded=gs://{report_bucket_name}/{dt_prefix}/summary.json")
    print(f"latest=gs://{report_bucket_name}/{latest_prefix}/summary.json")
    print(f"daily_summary_table={daily_table}")


if __name__ == "__main__":
    main()
