from __future__ import annotations

from pathlib import Path
import csv
import re


def reliability_band_from_p95(p95_delay_sec: int | None) -> str:
    if p95_delay_sec is None:
        return "unknown"
    if p95_delay_sec <= 60:
        return "leading"
    if p95_delay_sec <= 120:
        return "stable"
    if p95_delay_sec <= 240:
        return "watchlist"
    if p95_delay_sec <= 360:
        return "at-risk"
    return "critical"


def load_line_reliability_lookup(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, object]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            line = str(row.get("line", "")).strip()
            if not line:
                continue
            p95_delay_sec = int(float(row["p95_delay_sec"]))
            out[line] = {
                "risk_p95_delay_sec": p95_delay_sec,
                "avg_delay_sec": round(float(row["avg_delay_sec"]), 2),
                "sample_size": int(float(row["n"])),
                "confidence_tag": "derived",
                "evidence_level": "summary",
                "reliability_band": reliability_band_from_p95(p95_delay_sec),
            }
    return out


def enrich_reachable_stop(
    stop_row: dict[str, object],
    reliability_lookup: dict[str, dict[str, object]],
) -> dict[str, object]:
    line = str(stop_row.get("line", "")).strip()
    reliability = reliability_lookup.get(line, {})
    p95_delay_sec = reliability.get("risk_p95_delay_sec")
    return {
        **stop_row,
        "risk_p95_delay_sec": p95_delay_sec,
        "confidence_tag": reliability.get("confidence_tag", "unknown"),
        "evidence_level": reliability.get("evidence_level", "unknown"),
        "reliability_band": reliability.get(
            "reliability_band",
            reliability_band_from_p95(p95_delay_sec if isinstance(p95_delay_sec, int) else None),
        ),
    }


def load_stop_rows(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    if not path.exists():
        return {}, []
    rows: list[dict[str, str]] = []
    by_id: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
            stop_id = str(row.get("stop_id", "")).strip()
            if stop_id:
                by_id[stop_id] = row
    return by_id, rows


def find_stop_record(
    stop_id: str,
    stop_name: str,
    stop_by_id: dict[str, dict[str, str]],
    stop_rows: list[dict[str, str]],
) -> dict[str, str] | None:
    if stop_id and stop_id in stop_by_id:
        return stop_by_id[stop_id]
    target = stop_name.strip().lower()
    if not target:
        return None
    for row in stop_rows:
        current = str(row.get("stop_name", "")).strip().lower()
        if current == target or target in current:
            return row
    return None


def parse_week1_top_hubs(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        match = re.match(
            r"- (.+?) \(`([^`]+)`\): degree=([0-9]+), in=([0-9]+), out=([0-9]+)",
            line,
        )
        if not match:
            continue
        out.append(
            {
                "name": match.group(1),
                "stop_id": match.group(2),
                "degree": int(match.group(3)),
                "in_degree": int(match.group(4)),
                "out_degree": int(match.group(5)),
            }
        )
    return out


def load_vulnerable_nodes(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            out.append(
                {
                    "rank": int(float(row["rank"])),
                    "stop_id": row["stop_id"],
                    "degree": int(float(row["degree"])),
                    "betweenness_score": round(float(row["betweenness_score"]), 2),
                    "impact_delta_lcc": row["impact_delta_lcc"],
                    "planning_implication": row["planning_implication"],
                }
            )
    return out


def build_station_overlays(
    week1_summary_path: Path,
    vulnerable_nodes_path: Path,
    stops_path: Path,
) -> dict[str, list[dict[str, object]]]:
    top_hubs = parse_week1_top_hubs(week1_summary_path)
    vulnerable_nodes = load_vulnerable_nodes(vulnerable_nodes_path)
    stop_by_id, stop_rows = load_stop_rows(stops_path)

    hubs_payload: list[dict[str, object]] = []
    for hub in top_hubs[:10]:
        stop = find_stop_record(str(hub["stop_id"]), str(hub["name"]), stop_by_id, stop_rows)
        if stop is None:
            continue
        hubs_payload.append(
            {
                "stop_id": hub["stop_id"],
                "name": stop.get("stop_name") or hub["name"],
                "lat": float(stop["stop_lat"]),
                "lon": float(stop["stop_lon"]),
                "degree": hub["degree"],
                "layer": "hub",
            }
        )

    vulnerable_payload: list[dict[str, object]] = []
    for item in vulnerable_nodes[:10]:
        stop = find_stop_record(str(item["stop_id"]), "", stop_by_id, stop_rows)
        if stop is None:
            continue
        vulnerable_payload.append(
            {
                "stop_id": item["stop_id"],
                "name": stop.get("stop_name") or item["stop_id"],
                "lat": float(stop["stop_lat"]),
                "lon": float(stop["stop_lon"]),
                "betweenness_score": item["betweenness_score"],
                "impact_delta_lcc": item["impact_delta_lcc"],
                "layer": "vulnerable",
            }
        )

    return {"hubs": hubs_payload, "vulnerable_nodes": vulnerable_payload}
