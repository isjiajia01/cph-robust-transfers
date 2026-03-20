from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from urllib.parse import urlencode

from src.common.config import load_config
from src.common.io import write_csv
from src.realtime.collector import request_json, _json_or_error, _extract_location_id


DEFAULT_STATION_NAMES = [
    "Kobenhavn H",
    "Norreport St",
    "Osterport St",
    "Valby St",
    "Flintholm St",
    "Hellerup St",
    "Lyngby St",
    "Hvidovre St",
    "Ballerup St",
    "Roskilde St",
    "Kastrup Lufthavn St",
    "Orestad St",
    "Kobenhavn Syd St",
    "Kobenhavn Ny Ellebjerg St",
    "Gentofte St",
    "Svanemollen St",
    "Nordhavn St",
    "Holte St",
    "Hillerod St",
    "Taastrup St",
    "Glostrup St",
    "Herlev St",
    "Vanlose St",
    "Frederiksberg St",
    "Amagerbro St",
    "Christianshavn St",
    "Kongens Nytorv St",
    "Forum St",
    "Nyboder St",
    "Ishoj St",
]


def resolve_stop_ext_id(base_url: str, access_id: str, station_name: str, cfg) -> str | None:
    params = {"input": station_name, "format": "json", "accessId": access_id}
    url = f"{base_url.rstrip('/')}/location.name?{urlencode(params)}"
    res = request_json(
        url,
        timeout=cfg.http.timeout_sec,
        retries=cfg.http.max_retries,
        backoff_base=cfg.http.backoff_base_sec,
        backoff_max=cfg.http.backoff_max_sec,
    )
    payload = _json_or_error(res.body)
    return _extract_location_id(payload)


def validate_board(base_url: str, access_id: str, stop_ext_id: str, cfg) -> tuple[int, bool]:
    params = {"idList": stop_ext_id, "format": "json", "accessId": access_id}
    url = f"{base_url.rstrip('/')}/multiDepartureBoard?{urlencode(params)}"
    res = request_json(
        url,
        timeout=cfg.http.timeout_sec,
        retries=cfg.http.max_retries,
        backoff_base=cfg.http.backoff_base_sec,
        backoff_max=cfg.http.backoff_max_sec,
    )
    payload = _json_or_error(res.body)
    has_departure = False
    dep = payload.get("Departure") or payload.get("departures")
    if isinstance(dep, list):
        has_departure = len(dep) > 0
    elif isinstance(dep, dict):
        has_departure = True
    return res.status, has_departure


def read_station_names(path: Path | None) -> list[str]:
    if path is None:
        return DEFAULT_STATION_NAMES
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        out = []
        for row in reader:
            name = (row.get("station_name") or "").strip()
            if name:
                out.append(name)
        return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve and validate station stopExtId values")
    parser.add_argument("--base-url", default="https://www.rejseplanen.dk/api")
    parser.add_argument("--config", default="configs/pipeline.defaults.toml")
    parser.add_argument("--station-csv", default=None, help="CSV with column station_name")
    parser.add_argument("--out", default="configs/stations_seed.csv")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    access_id = os.getenv("REJSEPLANEN_API_KEY", "")
    if not access_id:
        raise SystemExit("Missing REJSEPLANEN_API_KEY")

    cfg = load_config(args.config)
    names = read_station_names(Path(args.station_csv) if args.station_csv else None)

    valid_rows: list[dict] = []
    seen_ids: set[str] = set()

    for name in names:
        stop_ext_id = resolve_stop_ext_id(args.base_url, access_id, name, cfg)
        if not stop_ext_id or stop_ext_id in seen_ids:
            continue
        status, has_dep = validate_board(args.base_url, access_id, stop_ext_id, cfg)
        if status == 200 and has_dep:
            seen_ids.add(stop_ext_id)
            valid_rows.append(
                {
                    "station_name": name,
                    "api_station_id": stop_ext_id,
                    "gtfs_stop_id": "UNKNOWN",
                    "weight": "0.5",
                }
            )
        if len(valid_rows) >= args.limit:
            break

    if not valid_rows:
        raise SystemExit("No valid stations resolved")

    write_csv(Path(args.out), valid_rows, ["station_name", "api_station_id", "gtfs_stop_id", "weight"])
    print(f"wrote={args.out} count={len(valid_rows)}")


if __name__ == "__main__":
    main()
