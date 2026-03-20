from __future__ import annotations

from datetime import datetime
from typing import Any


def _safe_get(d: dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _to_ts(date_str: str | None, time_str: str | None) -> str | None:
    if not date_str or not time_str:
        return None
    t = time_str.strip()
    if len(t) == 5:
        t = f"{t}:00"
    return f"{date_str}T{t}"


def _delay_sec(planned_ts: str | None, realtime_ts: str | None) -> int | None:
    if not planned_ts or not realtime_ts:
        return None
    try:
        p = datetime.fromisoformat(planned_ts)
        r = datetime.fromisoformat(realtime_ts)
        return int((r - p).total_seconds())
    except ValueError:
        return None


def parse_board_response(payload: dict[str, Any], obs_ts_utc: str, run_id: str) -> list[dict]:
    departures: list[dict] = []
    items = payload.get("Departure") or payload.get("departures") or []
    if isinstance(items, dict):
        items = [items]

    for item in items:
        planned_dep_ts = _to_ts(item.get("date"), item.get("time"))
        rt_time = item.get("rtTime") or item.get("realtimeTime")
        rt_date = item.get("rtDate") or item.get("realtimeDate") or item.get("date")
        realtime_dep_ts = _to_ts(rt_date, rt_time)
        delay_sec = _delay_sec(planned_dep_ts, realtime_dep_ts)
        journey_ref = (
            _safe_get(item, "JourneyDetailRef", "ref")
            or _safe_get(item, "journeyDetailRef", "ref")
            or item.get("journeyRef")
        )

        departures.append(
            {
                "obs_ts_utc": obs_ts_utc,
                "run_id": run_id,
                "station_gtfs_id": None,
                "api_station_id": item.get("stopid") or item.get("stopId"),
                "line": item.get("name") or item.get("line"),
                "mode": item.get("type") or item.get("mode"),
                "direction": item.get("direction"),
                "planned_dep_ts": planned_dep_ts,
                "realtime_dep_ts": realtime_dep_ts,
                "delay_sec": delay_sec,
                "journey_ref": journey_ref,
            }
        )
    return departures


def parse_journey_detail(payload: dict[str, Any], obs_ts_utc: str, run_id: str, journey_ref: str) -> list[dict]:
    stops = payload.get("Stops") or payload.get("stops") or payload.get("JourneyStop") or []
    if isinstance(stops, dict):
        stops = [stops]
    rows: list[dict] = []

    for idx, stop in enumerate(stops):
        a_date = stop.get("arrDate") or stop.get("date")
        a_time = stop.get("arrTime") or stop.get("time")
        d_date = stop.get("depDate") or stop.get("date")
        d_time = stop.get("depTime") or stop.get("time")

        ra_date = stop.get("rtArrDate") or a_date
        ra_time = stop.get("rtArrTime")
        rd_date = stop.get("rtDepDate") or d_date
        rd_time = stop.get("rtDepTime")
        planned_arr_ts = _to_ts(a_date, a_time)
        realtime_arr_ts = _to_ts(ra_date, ra_time)
        planned_dep_ts = _to_ts(d_date, d_time)
        realtime_dep_ts = _to_ts(rd_date, rd_time)

        rows.append(
            {
                "obs_ts_utc": obs_ts_utc,
                "run_id": run_id,
                "journey_ref": journey_ref,
                "seq": idx,
                "stop_api_id": stop.get("id") or stop.get("stopid") or stop.get("stopId"),
                "planned_arr_ts": planned_arr_ts,
                "realtime_arr_ts": realtime_arr_ts,
                "planned_dep_ts": planned_dep_ts,
                "realtime_dep_ts": realtime_dep_ts,
                "delay_arr_sec": _delay_sec(planned_arr_ts, realtime_arr_ts),
                "delay_dep_sec": _delay_sec(planned_dep_ts, realtime_dep_ts),
            }
        )
    return rows
