from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.common.config import load_config
from src.common.io import ensure_parent, utc_now_iso, write_csv
from src.realtime.parser import parse_board_response, parse_journey_detail
from src.realtime.rate_limit import TokenBucket


def _bigquery_table_schemas():
    try:
        from google.cloud import bigquery
    except Exception as exc:
        raise SystemExit(
            "google-cloud-bigquery is required for BigQuery loads. Install dependencies in runtime image."
        ) from exc

    schemas = {
        "departures": [
            bigquery.SchemaField("obs_ts_utc", "STRING"),
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("station_gtfs_id", "STRING"),
            bigquery.SchemaField("api_station_id", "STRING"),
            bigquery.SchemaField("line", "STRING"),
            bigquery.SchemaField("mode", "STRING"),
            bigquery.SchemaField("direction", "STRING"),
            bigquery.SchemaField("planned_dep_ts", "STRING"),
            bigquery.SchemaField("realtime_dep_ts", "STRING"),
            bigquery.SchemaField("delay_sec", "STRING"),
            bigquery.SchemaField("journey_ref", "STRING"),
        ],
        "journey_stops": [
            bigquery.SchemaField("obs_ts_utc", "STRING"),
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("journey_ref", "STRING"),
            bigquery.SchemaField("seq", "INTEGER"),
            bigquery.SchemaField("stop_api_id", "STRING"),
            bigquery.SchemaField("planned_arr_ts", "STRING"),
            bigquery.SchemaField("realtime_arr_ts", "STRING"),
            bigquery.SchemaField("planned_dep_ts", "STRING"),
            bigquery.SchemaField("realtime_dep_ts", "STRING"),
            bigquery.SchemaField("delay_arr_sec", "STRING"),
            bigquery.SchemaField("delay_dep_sec", "STRING"),
        ],
        "observations": [
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("trigger_id", "STRING"),
            bigquery.SchemaField("scheduled_ts_utc", "STRING"),
            bigquery.SchemaField("job_start_ts_utc", "STRING"),
            bigquery.SchemaField("job_end_ts_utc", "STRING"),
            bigquery.SchemaField("request_ts", "STRING"),
            bigquery.SchemaField("ingest_ts_utc", "STRING"),
            bigquery.SchemaField("endpoint", "STRING"),
            bigquery.SchemaField("station_batch", "STRING"),
            bigquery.SchemaField("status", "INTEGER"),
            bigquery.SchemaField("latency_ms", "INTEGER"),
            bigquery.SchemaField("records_emitted", "INTEGER"),
            bigquery.SchemaField("run_status", "STRING"),
            bigquery.SchemaField("collector_version", "STRING"),
            bigquery.SchemaField("sampling_target_version", "STRING"),
        ],
        "api_errors": [
            bigquery.SchemaField("obs_ts_utc", "STRING"),
            bigquery.SchemaField("ingest_ts_utc", "STRING"),
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("trigger_id", "STRING"),
            bigquery.SchemaField("endpoint", "STRING"),
            bigquery.SchemaField("http_code", "INTEGER"),
            bigquery.SchemaField("error_code", "STRING"),
            bigquery.SchemaField("message", "STRING"),
            bigquery.SchemaField("station_id", "STRING"),
            bigquery.SchemaField("journey_ref", "STRING"),
            bigquery.SchemaField("latency_ms", "INTEGER"),
            bigquery.SchemaField("retry_count", "INTEGER"),
            bigquery.SchemaField("request_id", "STRING"),
            bigquery.SchemaField("is_retry_final", "BOOLEAN"),
        ],
        "run_metrics": [
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("trigger_id", "STRING"),
            bigquery.SchemaField("scheduled_ts_utc", "STRING"),
            bigquery.SchemaField("job_start_ts_utc", "STRING"),
            bigquery.SchemaField("job_end_ts_utc", "STRING"),
            bigquery.SchemaField("duration_sec", "INTEGER"),
            bigquery.SchemaField("schedule_interval_sec", "INTEGER"),
            bigquery.SchemaField("station_count", "INTEGER"),
            bigquery.SchemaField("board_request_count", "INTEGER"),
            bigquery.SchemaField("journey_request_count", "INTEGER"),
            bigquery.SchemaField("success_count", "INTEGER"),
            bigquery.SchemaField("error_count", "INTEGER"),
            bigquery.SchemaField("status_2xx_count", "INTEGER"),
            bigquery.SchemaField("status_4xx_count", "INTEGER"),
            bigquery.SchemaField("status_5xx_count", "INTEGER"),
            bigquery.SchemaField("run_status", "STRING"),
            bigquery.SchemaField("collector_version", "STRING"),
            bigquery.SchemaField("sampling_target_version", "STRING"),
        ],
    }
    return bigquery, schemas


def _ensure_bq_tables(client, dataset: str, schemas: dict[str, list]) -> None:
    bigquery, _ = _bigquery_table_schemas()
    for table_name, schema in schemas.items():
        table_id = f"{client.project}.{dataset}.{table_name}"
        try:
            client.get_table(table_id)
        except Exception:
            client.create_table(bigquery.Table(table_id, schema=schema))


def _csv_has_data(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8", newline="") as f:
        next(f, None)
        return next(f, None) is not None


def _load_structured_dir_to_bq(local_dir: Path, dataset: str, project_id: str) -> None:
    bigquery, schemas = _bigquery_table_schemas()
    client = bigquery.Client(project=project_id)
    _ensure_bq_tables(client, dataset, schemas)

    job_config_by_table = {
        table_name: bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        for table_name, schema in schemas.items()
    }
    job_config_by_table["observations"].allow_jagged_rows = True
    job_config_by_table["api_errors"].allow_jagged_rows = True
    job_config_by_table["run_metrics"].allow_jagged_rows = True

    loaded_tables: list[str] = []
    for table_name in ("departures", "journey_stops", "observations", "api_errors", "run_metrics"):
        csv_path = local_dir / f"{table_name}.csv"
        if not _csv_has_data(csv_path):
            continue
        table_id = f"{client.project}.{dataset}.{table_name}"
        with csv_path.open("rb") as f:
            job = client.load_table_from_file(f, table_id, job_config=job_config_by_table[table_name])
        job.result()
        loaded_tables.append(table_name)
    print(f"bq_loaded_tables={','.join(loaded_tables) if loaded_tables else 'none'} dataset={client.project}.{dataset}")


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: str
    retries_used: int
    is_retry_final: bool


def request_json(url: str, timeout: int, retries: int, backoff_base: float, backoff_max: float) -> HttpResult:
    attempt = 0
    while True:
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=timeout) as resp:
                return HttpResult(
                    status=getattr(resp, "status", 200),
                    body=resp.read().decode("utf-8"),
                    retries_used=attempt,
                    is_retry_final=False,
                )
        except HTTPError as exc:
            status = exc.code
            body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            if attempt >= retries or (status < 500 and status not in (429,)):
                return HttpResult(
                    status=status,
                    body=body,
                    retries_used=attempt,
                    is_retry_final=attempt >= retries,
                )
        except URLError:
            if attempt >= retries:
                return HttpResult(status=0, body="", retries_used=attempt, is_retry_final=True)
        sleep_for = min(backoff_max, backoff_base * (2**attempt)) + random.uniform(0, 0.2)
        time.sleep(sleep_for)
        attempt += 1


def _json_or_error(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}


def _read_station_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _chunks(values: list[str], n: int) -> list[list[str]]:
    return [values[i : i + n] for i in range(0, len(values), n)]


def _normalize_station_id(value: str) -> str:
    v = value.strip()
    if v.isdigit():
        stripped = v.lstrip("0")
        return stripped or "0"
    return v


def _write_raw(path: Path, obj: dict) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=True) + "\n")


def _upload_dir_to_gcs(local_dir: Path, bucket_name: str, object_prefix: str) -> None:
    try:
        from google.cloud import storage
    except Exception as exc:
        raise SystemExit(
            "google-cloud-storage is required for GCS upload. Install dependencies in runtime image."
        ) from exc

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    uploaded = 0
    for file_path in sorted(local_dir.glob("*.csv")) + sorted(local_dir.glob("*.ndjson")):
        blob_name = f"{object_prefix.rstrip('/')}/{file_path.name}"
        bucket.blob(blob_name).upload_from_filename(str(file_path))
        uploaded += 1
    print(f"uploaded_files={uploaded} to gs://{bucket_name}/{object_prefix.rstrip('/')}")


def _extract_location_id(payload: dict) -> str | None:
    def _maybe_get_id(item: dict) -> str | None:
        if not isinstance(item, dict):
            return None
        for key in ("id", "extId", "stopid", "stopId"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    candidates = []
    for key in ("StopLocation", "stopLocationOrCoordLocation", "locations", "Location"):
        obj = payload.get(key)
        if isinstance(obj, list):
            candidates.extend(obj)
        elif isinstance(obj, dict):
            candidates.append(obj)

    loc_list = payload.get("LocationList")
    if isinstance(loc_list, dict):
        stop_loc = loc_list.get("StopLocation")
        if isinstance(stop_loc, list):
            candidates.extend(stop_loc)
        elif isinstance(stop_loc, dict):
            candidates.append(stop_loc)

    normalized: list[dict] = []
    for cand in candidates:
        if isinstance(cand, dict) and "StopLocation" in cand and isinstance(cand["StopLocation"], dict):
            normalized.append(cand["StopLocation"])
        elif isinstance(cand, dict):
            normalized.append(cand)

    for cand in normalized:
        found = _maybe_get_id(cand)
        if found:
            if found.startswith("A=") and "@L=" in found:
                # Prefer stable stopExtId when full HAFAS location IDs are returned.
                segment = found.split("@L=", 1)[1]
                ext_id = segment.split("@", 1)[0]
                if ext_id:
                    return ext_id
            return found
    return None


def _resolve_station_ids(rows: list[dict[str, str]], base_url: str, cfg, access_id: str) -> list[str]:
    out: list[str] = []
    for row in rows:
        station_name = (row.get("station_name") or "").strip()
        raw_id = (row.get("api_station_id") or "").strip()
        if raw_id:
            out.append(raw_id)
            continue
        if not station_name:
            continue
        params = {"input": station_name, "format": "json", "accessId": access_id}
        url = f"{base_url.rstrip('/')}/location.name?{urlencode(params)}"
        result = request_json(
            url,
            timeout=cfg.http.timeout_sec,
            retries=cfg.http.max_retries,
            backoff_base=cfg.http.backoff_base_sec,
            backoff_max=cfg.http.backoff_max_sec,
        )
        payload = _json_or_error(result.body)
        resolved = _extract_location_id(payload)
        if resolved:
            out.append(resolved)
    return out


def _parse_ts_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _scheduled_ts_utc(now_utc: datetime, interval_sec: int) -> datetime:
    env_val = os.getenv("SCHEDULED_TS_UTC", "").strip()
    if env_val:
        try:
            return _parse_ts_utc(env_val)
        except ValueError:
            pass
    step = max(60, int(interval_sec))
    epoch = int(now_utc.timestamp())
    floored = epoch - (epoch % step)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _sampling_target_version(config_path: Path, stations_path: Path) -> str:
    h = hashlib.sha1()
    for p in (config_path, stations_path):
        if p.exists():
            h.update(p.read_bytes())
        else:
            h.update(str(p).encode("utf-8"))
    return h.hexdigest()[:12]


def _extract_error(payload: dict) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return ("UNKNOWN", "")
    code = (
        str(payload.get("errorCode", "")).strip()
        or str(payload.get("error", "")).strip()
        or str(payload.get("code", "")).strip()
        or "UNKNOWN"
    )
    msg = (
        str(payload.get("errorText", "")).strip()
        or str(payload.get("errorMessage", "")).strip()
        or str(payload.get("message", "")).strip()
    )
    return (code, msg[:500])


def _dedupe_departures(rows: list[dict]) -> list[dict]:
    out: dict[tuple[str, str, str, str], dict] = {}
    for r in rows:
        key = (
            str(r.get("run_id", "")),
            str(r.get("api_station_id", "")),
            str(r.get("journey_ref", "")),
            str(r.get("planned_dep_ts", "")),
        )
        out[key] = r
    return list(out.values())


def _finalize_observation_rows(obs_rows: list[dict], job_end_ts: str, run_status: str) -> list[dict]:
    out: list[dict] = []
    for row in obs_rows:
        updated = dict(row)
        updated["job_end_ts_utc"] = job_end_ts
        updated["run_status"] = run_status
        out.append(updated)
    return out


def _build_run_metrics_row(
    *,
    run_id: str,
    trigger_id: str,
    scheduled_ts: str,
    job_start_ts: str,
    job_end_ts: str,
    duration_sec: int,
    schedule_interval_sec: int,
    station_count: int,
    board_request_count: int,
    journey_request_count: int,
    success_count: int,
    error_count: int,
    status_2xx_count: int,
    status_4xx_count: int,
    status_5xx_count: int,
    run_status: str,
    collector_version: str,
    sampling_target_version: str,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "trigger_id": trigger_id,
        "scheduled_ts_utc": scheduled_ts,
        "job_start_ts_utc": job_start_ts,
        "job_end_ts_utc": job_end_ts,
        "duration_sec": duration_sec,
        "schedule_interval_sec": schedule_interval_sec,
        "station_count": station_count,
        "board_request_count": board_request_count,
        "journey_request_count": journey_request_count,
        "success_count": success_count,
        "error_count": error_count,
        "status_2xx_count": status_2xx_count,
        "status_4xx_count": status_4xx_count,
        "status_5xx_count": status_5xx_count,
        "run_status": run_status,
        "collector_version": collector_version,
        "sampling_target_version": sampling_target_version,
    }


def run_once(config_path: Path, stations_path: Path, base_url: str, access_id: str) -> None:
    cfg = load_config(config_path)
    job_start_dt = datetime.now(timezone.utc)
    job_start_ts = job_start_dt.isoformat().replace("+00:00", "Z")
    scheduled_dt = _scheduled_ts_utc(job_start_dt, cfg.sampling.interval_sec)
    scheduled_ts = scheduled_dt.isoformat().replace("+00:00", "Z")
    obs_ts = utc_now_iso()
    run_id = scheduled_dt.strftime("%Y%m%dT%H%M")
    trigger_id = os.getenv("TRIGGER_ID", "").strip() or os.getenv("CLOUD_RUN_EXECUTION", "").strip() or run_id
    collector_version = os.getenv("COLLECTOR_VERSION", "").strip() or "unknown"
    ingest_ts = utc_now_iso()
    sampling_target_version = _sampling_target_version(config_path, stations_path)

    raw_dir = Path(cfg.storage.raw_dir) / f"dt={obs_ts[:10]}" / f"run_id={run_id}"
    structured_dir = Path(cfg.storage.structured_dir) / f"dt={obs_ts[:10]}" / f"run_id={run_id}"

    station_rows = _read_station_rows(stations_path)
    stations = _resolve_station_ids(station_rows, base_url, cfg, access_id)
    print(f"resolved_stations={len(stations)} sample={stations[:5]}")
    batch_size = max(1, cfg.sampling.station_batch_size)
    bucket = TokenBucket(rate_per_sec=2.0, capacity=4)

    departures_all: list[dict] = []
    journey_rows_all: list[dict] = []
    obs_rows: list[dict] = []
    error_rows: list[dict] = []
    board_request_count = 0
    journey_request_count = 0
    status_2xx_count = 0
    status_4xx_count = 0
    status_5xx_count = 0

    for batch in _chunks(stations, batch_size):
        board_request_count += 1
        request_id = str(uuid.uuid4())
        bucket.acquire()
        params = {"idList": "|".join(batch), "accessId": access_id, "format": "json"}
        url = f"{base_url.rstrip('/')}/multiDepartureBoard?{urlencode(params)}"
        t0 = time.monotonic()
        result = request_json(
            url,
            timeout=cfg.http.timeout_sec,
            retries=cfg.http.max_retries,
            backoff_base=cfg.http.backoff_base_sec,
            backoff_max=cfg.http.backoff_max_sec,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        payload = _json_or_error(result.body)
        # Retry once with normalized numeric station IDs if API rejects LOCATION.
        if result.status == 400 and isinstance(payload, dict) and payload.get("errorCode") == "SVC_LOC":
            normalized_batch = [_normalize_station_id(x) for x in batch]
            if normalized_batch != batch:
                params_retry = {"idList": "|".join(normalized_batch), "accessId": access_id, "format": "json"}
                retry_url = f"{base_url.rstrip('/')}/multiDepartureBoard?{urlencode(params_retry)}"
                result = request_json(
                    retry_url,
                    timeout=cfg.http.timeout_sec,
                    retries=cfg.http.max_retries,
                    backoff_base=cfg.http.backoff_base_sec,
                    backoff_max=cfg.http.backoff_max_sec,
                )
                payload = _json_or_error(result.body)
                batch = normalized_batch

        _write_raw(
            raw_dir / "board.ndjson",
            {
                "obs_ts_utc": obs_ts,
                "scheduled_ts_utc": scheduled_ts,
                "run_id": run_id,
                "trigger_id": trigger_id,
                "endpoint": "multiDepartureBoard",
                "request_id": request_id,
                "station_batch": batch,
                "status": result.status,
                "retries_used": result.retries_used,
                "is_retry_final": result.is_retry_final,
                "payload": payload,
            },
        )

        departures = parse_board_response(payload, obs_ts, run_id)
        departures_all.extend(departures)
        obs_rows.append(
            {
                "run_id": run_id,
                "trigger_id": trigger_id,
                "scheduled_ts_utc": scheduled_ts,
                "job_start_ts_utc": job_start_ts,
                "request_ts": obs_ts,
                "ingest_ts_utc": ingest_ts,
                "endpoint": "multiDepartureBoard",
                "station_batch": "|".join(batch),
                "status": result.status,
                "latency_ms": latency_ms,
                "records_emitted": len(departures),
                "collector_version": collector_version,
                "sampling_target_version": sampling_target_version,
            }
        )
        if 200 <= result.status < 300:
            status_2xx_count += 1
        elif 400 <= result.status < 500:
            status_4xx_count += 1
        elif result.status >= 500 or result.status == 0:
            status_5xx_count += 1
        if result.status < 200 or result.status >= 300:
            error_code, message = _extract_error(payload)
            error_rows.append(
                {
                    "obs_ts_utc": obs_ts,
                    "ingest_ts_utc": ingest_ts,
                    "run_id": run_id,
                    "trigger_id": trigger_id,
                    "endpoint": "multiDepartureBoard",
                    "http_code": result.status,
                    "error_code": error_code,
                    "message": message,
                    "station_id": "|".join(batch),
                    "journey_ref": "",
                    "latency_ms": latency_ms,
                    "retry_count": result.retries_used,
                    "request_id": request_id,
                    "is_retry_final": "1" if result.is_retry_final else "0",
                }
            )

        refs = [d["journey_ref"] for d in departures if d.get("journey_ref")]
        refs = refs[: cfg.sampling.max_journey_detail_per_cycle]

        for ref in refs:
            journey_request_count += 1
            jd_request_id = str(uuid.uuid4())
            bucket.acquire()
            jd_url = f"{base_url.rstrip('/')}/journeyDetail?{urlencode({'ref': ref, 'accessId': access_id, 'format': 'json'})}"
            jd_t0 = time.monotonic()
            jd_result = request_json(
                jd_url,
                timeout=cfg.http.timeout_sec,
                retries=cfg.http.max_retries,
                backoff_base=cfg.http.backoff_base_sec,
                backoff_max=cfg.http.backoff_max_sec,
            )
            jd_latency_ms = int((time.monotonic() - jd_t0) * 1000)
            jd_payload = _json_or_error(jd_result.body)
            _write_raw(
                raw_dir / "journey_detail.ndjson",
                {
                    "obs_ts_utc": obs_ts,
                    "scheduled_ts_utc": scheduled_ts,
                    "run_id": run_id,
                    "trigger_id": trigger_id,
                    "endpoint": "journeyDetail",
                    "journey_ref": ref,
                    "request_id": jd_request_id,
                    "status": jd_result.status,
                    "retries_used": jd_result.retries_used,
                    "is_retry_final": jd_result.is_retry_final,
                    "payload": jd_payload,
                },
            )
            if 200 <= jd_result.status < 300:
                status_2xx_count += 1
            elif 400 <= jd_result.status < 500:
                status_4xx_count += 1
            elif jd_result.status >= 500 or jd_result.status == 0:
                status_5xx_count += 1
            if jd_result.status < 200 or jd_result.status >= 300:
                error_code, message = _extract_error(jd_payload)
                error_rows.append(
                    {
                        "obs_ts_utc": obs_ts,
                        "ingest_ts_utc": ingest_ts,
                        "run_id": run_id,
                        "trigger_id": trigger_id,
                        "endpoint": "journeyDetail",
                        "http_code": jd_result.status,
                        "error_code": error_code,
                        "message": message,
                        "station_id": "",
                        "journey_ref": ref,
                        "latency_ms": jd_latency_ms,
                        "retry_count": jd_result.retries_used,
                        "request_id": jd_request_id,
                        "is_retry_final": "1" if jd_result.is_retry_final else "0",
                    }
                )
            journey_rows_all.extend(parse_journey_detail(jd_payload, obs_ts, run_id, ref))

    departures_all = _dedupe_departures(departures_all)
    departures_path = structured_dir / "departures.csv"
    journey_path = structured_dir / "journey_stops.csv"
    obs_path = structured_dir / "observations.csv"
    errors_path = structured_dir / "api_errors.csv"
    run_metrics_path = structured_dir / "run_metrics.csv"

    write_csv(
        departures_path,
        departures_all,
        [
            "obs_ts_utc",
            "run_id",
            "station_gtfs_id",
            "api_station_id",
            "line",
            "mode",
            "direction",
            "planned_dep_ts",
            "realtime_dep_ts",
            "delay_sec",
            "journey_ref",
        ],
    )
    write_csv(
        journey_path,
        journey_rows_all,
        [
            "obs_ts_utc",
            "run_id",
            "journey_ref",
            "seq",
            "stop_api_id",
            "planned_arr_ts",
            "realtime_arr_ts",
            "planned_dep_ts",
            "realtime_dep_ts",
            "delay_arr_sec",
            "delay_dep_sec",
        ],
    )
    write_csv(
        errors_path,
        error_rows,
        [
            "obs_ts_utc",
            "ingest_ts_utc",
            "run_id",
            "trigger_id",
            "endpoint",
            "http_code",
            "error_code",
            "message",
            "station_id",
            "journey_ref",
            "latency_ms",
            "retry_count",
            "request_id",
            "is_retry_final",
        ],
    )
    job_end_dt = datetime.now(timezone.utc)
    job_end_ts = job_end_dt.isoformat().replace("+00:00", "Z")
    duration_sec = int((job_end_dt - job_start_dt).total_seconds())
    success_count = status_2xx_count
    error_count = status_4xx_count + status_5xx_count
    run_status = "success" if error_count == 0 else ("failed" if success_count == 0 else "partial")
    obs_rows = _finalize_observation_rows(obs_rows, job_end_ts=job_end_ts, run_status=run_status)
    write_csv(
        obs_path,
        obs_rows,
        [
            "run_id",
            "trigger_id",
            "scheduled_ts_utc",
            "job_start_ts_utc",
            "job_end_ts_utc",
            "request_ts",
            "ingest_ts_utc",
            "endpoint",
            "station_batch",
            "status",
            "latency_ms",
            "records_emitted",
            "run_status",
            "collector_version",
            "sampling_target_version",
        ],
    )
    write_csv(
        run_metrics_path,
        [
            _build_run_metrics_row(
                run_id=run_id,
                trigger_id=trigger_id,
                scheduled_ts=scheduled_ts,
                job_start_ts=job_start_ts,
                job_end_ts=job_end_ts,
                duration_sec=duration_sec,
                schedule_interval_sec=cfg.sampling.interval_sec,
                station_count=len(stations),
                board_request_count=board_request_count,
                journey_request_count=journey_request_count,
                success_count=success_count,
                error_count=error_count,
                status_2xx_count=status_2xx_count,
                status_4xx_count=status_4xx_count,
                status_5xx_count=status_5xx_count,
                run_status=run_status,
                collector_version=collector_version,
                sampling_target_version=sampling_target_version,
            )
        ],
        [
            "run_id",
            "trigger_id",
            "scheduled_ts_utc",
            "job_start_ts_utc",
            "job_end_ts_utc",
            "duration_sec",
            "schedule_interval_sec",
            "station_count",
            "board_request_count",
            "journey_request_count",
            "success_count",
            "error_count",
            "status_2xx_count",
            "status_4xx_count",
            "status_5xx_count",
            "run_status",
            "collector_version",
            "sampling_target_version",
        ],
    )

    if error_rows:
        code_counts = Counter(str(r.get("error_code", "") or "UNKNOWN") for r in error_rows)
        http_counts = Counter(str(r.get("http_code", "") or "0") for r in error_rows)
        print(
            json.dumps(
                {
                    "event": "api_error_summary",
                    "run_id": run_id,
                    "trigger_id": trigger_id,
                    "scheduled_ts_utc": scheduled_ts,
                    "error_code_counts": dict(sorted(code_counts.items())),
                    "http_code_counts": dict(sorted(http_counts.items())),
                    "error_row_count": len(error_rows),
                },
                ensure_ascii=True,
            )
        )

    gcs_raw_bucket = os.getenv("GCS_BUCKET_RAW", "").strip()
    gcs_structured_bucket = os.getenv("GCS_BUCKET_STRUCTURED", "").strip()
    bq_project_id = os.getenv("PROJECT_ID", "").strip()
    bq_dataset = os.getenv("BQ_DATASET", "cph_rt").strip()
    if gcs_raw_bucket:
        _upload_dir_to_gcs(raw_dir, gcs_raw_bucket, f"realtime_raw/dt={obs_ts[:10]}/run_id={run_id}")
    if gcs_structured_bucket:
        _upload_dir_to_gcs(
            structured_dir,
            gcs_structured_bucket,
            f"structured/dt={obs_ts[:10]}/run_id={run_id}",
        )
    if bq_project_id:
        _load_structured_dir_to_bq(structured_dir, bq_dataset, bq_project_id)

    print(f"run_id={run_id}")
    print(f"trigger_id={trigger_id}")
    print(f"scheduled_ts_utc={scheduled_ts}")
    print(raw_dir)
    print(structured_dir)
    if gcs_raw_bucket:
        print(f"uploaded_raw=gs://{gcs_raw_bucket}/realtime_raw/dt={obs_ts[:10]}/run_id={run_id}")
    if gcs_structured_bucket:
        print(f"uploaded_structured=gs://{gcs_structured_bucket}/structured/dt={obs_ts[:10]}/run_id={run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect realtime board and journey data")
    parser.add_argument("--config", default="configs/pipeline.defaults.toml")
    parser.add_argument("--stations", default="configs/stations_seed.csv")
    parser.add_argument("--base-url", required=True, help="Rejseplanen API base URL")
    parser.add_argument("--once", action="store_true", help="Run one collection cycle")
    args = parser.parse_args()

    access_id = os.getenv("REJSEPLANEN_API_KEY", "")
    if not access_id:
        raise SystemExit("Missing REJSEPLANEN_API_KEY environment variable")

    if args.once:
        run_once(Path(args.config), Path(args.stations), args.base_url, access_id)
        return

    cfg = load_config(args.config)
    while True:
        run_once(Path(args.config), Path(args.stations), args.base_url, access_id)
        time.sleep(cfg.sampling.interval_sec)


if __name__ == "__main__":
    main()
