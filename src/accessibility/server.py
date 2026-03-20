from __future__ import annotations

import argparse
import json
import mimetypes
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

from src.accessibility.cache import (
    JsonCache,
    ReachabilityQuery,
    build_location_search_cache_key,
    build_reachability_cache_key,
    normalize_modes,
)
from src.accessibility.rejseplanen_client import OriginRef, RejseplanenAPIConfig, RejseplanenClient
from src.accessibility.transform import (
    build_station_overlays,
    enrich_reachable_stop,
    load_line_reliability_lookup,
)
from src.common.io import utc_now_iso


@dataclass(frozen=True)
class CacheConfig:
    root_dir: Path
    memory_ttl_sec: int
    disk_ttl_sec: int
    location_search_ttl_sec: int
    reachability_bucket_minutes: int


@dataclass(frozen=True)
class FrontendConfig:
    default_city: str
    default_modes: tuple[str, ...]
    show_hubs_overlay: bool
    show_vulnerable_overlay: bool
    default_page_size: int
    max_page_size: int
    max_result_window: int
    default_sort_by: str
    default_reliability_filter: str
    default_bucket_filter: str
    overlay_min_lat: float
    overlay_max_lat: float
    overlay_min_lon: float
    overlay_max_lon: float
    overlay_scope_label: str


@dataclass(frozen=True)
class AccessibilityConfig:
    timezone: str
    cache: CacheConfig
    api: RejseplanenAPIConfig
    frontend: FrontendConfig
    static_dir: Path
    reliability_csv: Path
    week1_summary_path: Path
    vulnerable_nodes_path: Path
    stops_path: Path


def _parse_simple_toml_value(raw: str) -> object:
    value = raw.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_simple_toml_value(part.strip()) for part in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        return value


def _load_simple_toml_text(text: str) -> dict[str, object]:
    result: dict[str, object] = {}
    current: dict[str, object] = result
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            section = result.setdefault(section_name, {})
            if not isinstance(section, dict):
                raise ValueError(f"Invalid section {section_name}")
            current = section
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip()] = _parse_simple_toml_value(value)
    return result


def _load_toml(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)
    return _load_simple_toml_text(text)


def load_accessibility_config(path: Path) -> AccessibilityConfig:
    raw = _load_toml(path)
    root = path.resolve().parents[1]
    cache_section = raw.get("cache", {})
    api_section = raw.get("api", {})
    frontend_section = raw.get("frontend", {})

    return AccessibilityConfig(
        timezone=str(raw.get("timezone", "Europe/Copenhagen")),
        cache=CacheConfig(
            root_dir=(root / str(cache_section.get("root_dir", "data/cache/accessibility"))).resolve(),
            memory_ttl_sec=int(cache_section.get("memory_ttl_sec", 900)),
            disk_ttl_sec=int(cache_section.get("disk_ttl_sec", 3600)),
            location_search_ttl_sec=int(cache_section.get("location_search_ttl_sec", 86400)),
            reachability_bucket_minutes=int(cache_section.get("reachability_bucket_minutes", 5)),
        ),
        api=RejseplanenAPIConfig(
            base_url=str(api_section.get("base_url", "https://www.rejseplanen.dk/api")),
            request_timeout_sec=int(api_section.get("request_timeout_sec", 15)),
            location_search_limit=int(api_section.get("location_search_limit", 8)),
            max_minutes_default=int(api_section.get("max_minutes_default", 45)),
            max_changes_default=int(api_section.get("max_changes_default", 2)),
            access_id_env=str(api_section.get("access_id_env", "REJSEPLANEN_API_KEY")),
            access_id_query_param=str(api_section.get("access_id_query_param", "accessId")),
            format_param=str(api_section.get("format_param", "format")),
            format_value=str(api_section.get("format_value", "json")),
            location_search_path=str(api_section.get("location_search_path", "location.name")),
            location_search_query_param=str(api_section.get("location_search_query_param", "input")),
            location_search_limit_param=str(api_section.get("location_search_limit_param", "maxNo")),
            reachability_path=str(api_section.get("reachability_path", "reachability")),
            reachability_origin_id_param=str(api_section.get("reachability_origin_id_param", "originId")),
            reachability_origin_lat_param=str(api_section.get("reachability_origin_lat_param", "originCoordLat")),
            reachability_origin_lon_param=str(api_section.get("reachability_origin_lon_param", "originCoordLong")),
            reachability_date_param=str(api_section.get("reachability_date_param", "date")),
            reachability_time_param=str(api_section.get("reachability_time_param", "time")),
            reachability_duration_param=str(api_section.get("reachability_duration_param", "duration")),
            reachability_max_changes_param=str(api_section.get("reachability_max_changes_param", "maxChange")),
            reachability_modes_param=str(api_section.get("reachability_modes_param", "products")),
            mode_separator=str(api_section.get("mode_separator", ",")),
        ),
        frontend=FrontendConfig(
            default_city=str(frontend_section.get("default_city", "Copenhagen")),
            default_modes=tuple(str(x) for x in frontend_section.get("default_modes", ["train", "metro", "bus"])),
            show_hubs_overlay=bool(frontend_section.get("show_hubs_overlay", True)),
            show_vulnerable_overlay=bool(frontend_section.get("show_vulnerable_overlay", True)),
            default_page_size=int(frontend_section.get("default_page_size", 80)),
            max_page_size=int(frontend_section.get("max_page_size", 250)),
            max_result_window=int(frontend_section.get("max_result_window", 1200)),
            default_sort_by=str(frontend_section.get("default_sort_by", "quality_desc")),
            default_reliability_filter=str(frontend_section.get("default_reliability_filter", "all")),
            default_bucket_filter=str(frontend_section.get("default_bucket_filter", "all")),
            overlay_min_lat=float(frontend_section.get("overlay_min_lat", 55.55)),
            overlay_max_lat=float(frontend_section.get("overlay_max_lat", 55.82)),
            overlay_min_lon=float(frontend_section.get("overlay_min_lon", 12.05)),
            overlay_max_lon=float(frontend_section.get("overlay_max_lon", 12.72)),
            overlay_scope_label=str(frontend_section.get("overlay_scope_label", "Copenhagen only")),
        ),
        static_dir=(root / str(raw.get("static_dir", frontend_section.get("static_dir", "web/accessibility")))).resolve(),
        reliability_csv=(root / str(raw.get("reliability_csv", frontend_section.get("reliability_csv", "data/analysis/week3_line_reliability_rank.csv")))).resolve(),
        week1_summary_path=(root / str(raw.get("week1_summary_path", frontend_section.get("week1_summary_path", "docs/week1_summary.md")))).resolve(),
        vulnerable_nodes_path=(root / str(raw.get("vulnerable_nodes_path", frontend_section.get("vulnerable_nodes_path", "results/robustness/top10_vulnerable_nodes.csv")))).resolve(),
        stops_path=(root / str(raw.get("stops_path", frontend_section.get("stops_path", "data/gtfs/parsed/20260302/stops.csv")))).resolve(),
    )


class AccessibilityService:
    def __init__(self, cfg: AccessibilityConfig) -> None:
        self.cfg = cfg
        self.cache = JsonCache(cfg.cache.root_dir)
        self.client = RejseplanenClient(cfg.api)
        self.line_reliability_lookup = load_line_reliability_lookup(cfg.reliability_csv)
        raw_overlays = build_station_overlays(
            week1_summary_path=cfg.week1_summary_path,
            vulnerable_nodes_path=cfg.vulnerable_nodes_path,
            stops_path=cfg.stops_path,
        )
        self.station_overlays = filter_overlays_to_bounds(
            raw_overlays,
            min_lat=cfg.frontend.overlay_min_lat,
            max_lat=cfg.frontend.overlay_max_lat,
            min_lon=cfg.frontend.overlay_min_lon,
            max_lon=cfg.frontend.overlay_max_lon,
        )

    def health(self) -> dict[str, object]:
        return {
            "ok": True,
            "timezone": self.cfg.timezone,
            "has_labs_key": bool(os.getenv(self.cfg.api.access_id_env, "").strip()),
            "cache_root": str(self.cfg.cache.root_dir),
            "static_dir": str(self.cfg.static_dir),
            "generated_at_utc": utc_now_iso(),
        }

    def frontend_bootstrap(self) -> dict[str, object]:
        return {
            "timezone": self.cfg.timezone,
            "default_city": self.cfg.frontend.default_city,
            "default_modes": list(self.cfg.frontend.default_modes),
            "show_hubs_overlay": self.cfg.frontend.show_hubs_overlay,
            "show_vulnerable_overlay": self.cfg.frontend.show_vulnerable_overlay,
            "default_page_size": self.cfg.frontend.default_page_size,
            "max_page_size": self.cfg.frontend.max_page_size,
            "max_result_window": self.cfg.frontend.max_result_window,
            "default_sort_by": self.cfg.frontend.default_sort_by,
            "default_reliability_filter": self.cfg.frontend.default_reliability_filter,
            "default_bucket_filter": self.cfg.frontend.default_bucket_filter,
            "overlay_scope_label": self.cfg.frontend.overlay_scope_label,
        }

    def station_overlay_payload(self) -> dict[str, object]:
        return {
            "generated_at_utc": utc_now_iso(),
            "hubs": self.station_overlays["hubs"],
            "vulnerable_nodes": self.station_overlays["vulnerable_nodes"],
        }

    def handle_location_search(self, query: str, limit: int) -> dict[str, object]:
        cache_key = build_location_search_cache_key(query, limit)
        ttl_sec = min(self.cfg.cache.location_search_ttl_sec, self.cfg.cache.disk_ttl_sec)
        cached = self.cache.get(cache_key, ttl_sec=ttl_sec)
        if cached is not None:
            return {
                "query": query,
                "items": cached.payload["items"],
                "cache": {
                    "hit": True,
                    "source": cached.source,
                    "stale": cached.stale,
                    "age_sec": cached.age_sec,
                },
            }

        upstream = self.client.location_search(query=query, limit=limit)
        payload = {
            "items": upstream.normalized_items,
            "request_url": upstream.request_url,
            "generated_at_utc": utc_now_iso(),
        }
        self.cache.set(cache_key, payload)
        return {
            "query": query,
            "items": upstream.normalized_items,
            "cache": {"hit": False, "source": "upstream", "stale": False, "age_sec": 0},
        }

    def handle_reachability(self, body: dict[str, Any]) -> dict[str, object]:
        origin_body = body.get("origin") or {}
        if not isinstance(origin_body, dict):
            raise ValueError("origin must be an object")
        origin = OriginRef(
            id=str(origin_body.get("id", "")).strip(),
            type=str(origin_body.get("type", "stop")).strip() or "stop",
            lat=float(origin_body["lat"]) if origin_body.get("lat") is not None else None,
            lon=float(origin_body["lon"]) if origin_body.get("lon") is not None else None,
        )
        depart_at_local = str(body.get("depart_at_local", "")).strip()
        if not depart_at_local:
            raise ValueError("depart_at_local is required")
        max_minutes = int(body.get("max_minutes", 45))
        max_changes = int(body.get("max_changes", 2))
        page = max(1, int(body.get("page", 1)))
        per_page = int(body.get("per_page", self.cfg.frontend.default_page_size))
        per_page = max(1, min(per_page, self.cfg.frontend.max_page_size))
        sort_by = str(body.get("sort_by", self.cfg.frontend.default_sort_by)).strip() or self.cfg.frontend.default_sort_by
        reliability_filter = (
            str(body.get("reliability_filter", self.cfg.frontend.default_reliability_filter)).strip()
            or self.cfg.frontend.default_reliability_filter
        )
        bucket_filter = (
            str(body.get("bucket_filter", self.cfg.frontend.default_bucket_filter)).strip()
            or self.cfg.frontend.default_bucket_filter
        )
        direct_only = bool(body.get("direct_only", False))
        modes = normalize_modes(tuple(body.get("modes", self.cfg.frontend.default_modes)))
        origin_key = origin.id or (
            f"{origin.lat:.4f},{origin.lon:.4f}" if origin.lat is not None and origin.lon is not None else ""
        )
        if not origin_key:
            raise ValueError("origin id or coordinates are required")

        query = ReachabilityQuery(
            origin_key=origin_key,
            depart_at_local=depart_at_local,
            max_minutes=max_minutes,
            modes=modes,
            max_changes=max_changes,
        )
        cache_key = build_reachability_cache_key(
            query,
            bucket_minutes=self.cfg.cache.reachability_bucket_minutes,
            version="v2",
        )
        ttl_sec = self.cfg.cache.disk_ttl_sec
        cached = self.cache.get(cache_key, ttl_sec=ttl_sec)
        if cached is not None:
            rows = annotate_reachability_window(stored_reachability_rows(cached.payload), max_minutes=max_minutes)
            summary = summarize_reachability_window(rows, max_minutes=max_minutes)
            paged = paginate_reachability_results(
                apply_result_controls(
                    rows,
                    sort_by=sort_by,
                    reliability_filter=reliability_filter,
                    bucket_filter=bucket_filter,
                    direct_only=direct_only,
                ),
                page=page,
                per_page=per_page,
                max_result_window=self.cfg.frontend.max_result_window,
            )
            return {
                "query": cached.payload["query"],
                "stats": {
                    **paged["stats"],
                    **cached.payload.get("stats", {}),
                    "cache_status": "hit",
                    "cache_source": cached.source,
                    "cache_age_sec": cached.age_sec,
                    "sort_by": sort_by,
                    "reliability_filter": reliability_filter,
                    "bucket_filter": bucket_filter,
                    "direct_only": direct_only,
                },
                "reliability_summary": summary,
                "map_stops": paged["map_stops"],
                "reachable_stops": paged["reachable_stops"],
            }

        stale = self.cache.get(cache_key, ttl_sec=ttl_sec, allow_stale=True)
        try:
            upstream = self.client.reachability_search(origin=origin, query=query)
            reachable_stops = [
                enrich_reachable_stop(stop_row=item, reliability_lookup=self.line_reliability_lookup)
                for item in upstream.normalized_items
            ]
            reachable_stops = annotate_reachability_window(reachable_stops, max_minutes=max_minutes)
            filtered_sorted = apply_result_controls(
                reachable_stops,
                sort_by=sort_by,
                reliability_filter=reliability_filter,
                bucket_filter=bucket_filter,
                direct_only=direct_only,
            )
            paged = paginate_reachability_results(
                filtered_sorted,
                page=page,
                per_page=per_page,
                max_result_window=self.cfg.frontend.max_result_window,
            )
            summary = summarize_reachability_window(reachable_stops, max_minutes=max_minutes)
            payload = {
                "query": {
                    "origin_id": origin.id,
                    "origin_type": origin.type,
                    "depart_at_local": depart_at_local,
                    "max_minutes": max_minutes,
                    "modes": list(modes),
                    "max_changes": max_changes,
                },
                "stats": {
                    "generated_at_utc": utc_now_iso(),
                    "request_url": upstream.request_url,
                    "upstream_reachable_stop_count": len(reachable_stops),
                },
                "reliability_summary": summary,
                "all_reachable_stops": reachable_stops,
            }
            self.cache.set(cache_key, payload)
            return {
                "query": payload["query"],
                "stats": {
                    **paged["stats"],
                    **payload["stats"],
                    "cache_status": "miss",
                    "cache_source": "upstream",
                    "cache_age_sec": 0,
                    "sort_by": sort_by,
                    "reliability_filter": reliability_filter,
                    "bucket_filter": bucket_filter,
                    "direct_only": direct_only,
                },
                "reliability_summary": summary,
                "map_stops": paged["map_stops"],
                "reachable_stops": paged["reachable_stops"],
            }
        except Exception:
            if stale is not None:
                rows = annotate_reachability_window(stored_reachability_rows(stale.payload), max_minutes=max_minutes)
                summary = summarize_reachability_window(rows, max_minutes=max_minutes)
                paged = paginate_reachability_results(
                    apply_result_controls(
                        rows,
                        sort_by=sort_by,
                        reliability_filter=reliability_filter,
                        bucket_filter=bucket_filter,
                        direct_only=direct_only,
                    ),
                    page=page,
                    per_page=per_page,
                    max_result_window=self.cfg.frontend.max_result_window,
                )
                return {
                    "query": stale.payload["query"],
                    "stats": {
                        **paged["stats"],
                        **stale.payload.get("stats", {}),
                        "cache_status": "stale",
                        "cache_source": stale.source,
                        "cache_age_sec": stale.age_sec,
                        "sort_by": sort_by,
                        "reliability_filter": reliability_filter,
                        "bucket_filter": bucket_filter,
                        "direct_only": direct_only,
                    },
                    "reliability_summary": summary,
                    "map_stops": paged["map_stops"],
                    "reachable_stops": paged["reachable_stops"],
                }
            raise


def bucket_label(minutes: int) -> str:
    if minutes <= 15:
        return "0-15"
    if minutes <= 30:
        return "16-30"
    if minutes <= 45:
        return "31-45"
    return "46+"


def summarize_reachability_window(
    stops: list[dict[str, object]],
    *,
    max_minutes: int,
) -> dict[str, object]:
    scheduled_count = 0
    robust_count = 0
    high_confidence_count = 0
    total_loss = 0
    critical_or_risky = 0

    for row in stops:
        travel_time_min = int(row.get("travel_time_min") or 0)
        p95_delay_sec = row.get("risk_p95_delay_sec")
        robust_travel_time = travel_time_min + (
            max(0, int(p95_delay_sec)) / 60.0 if isinstance(p95_delay_sec, int) else 0.0
        )
        if travel_time_min <= max_minutes:
            scheduled_count += 1
        if robust_travel_time <= max_minutes:
            robust_count += 1
        if str(row.get("evidence_level", "")) in {"medium", "high", "summary"}:
            high_confidence_count += 1
        if travel_time_min <= max_minutes and robust_travel_time > max_minutes:
            total_loss += 1
        if str(row.get("reliability_band", "unknown")) in {"at-risk", "critical"}:
            critical_or_risky += 1

    return {
        "scheduled_accessible_count": scheduled_count,
        "robust_accessible_count": robust_count,
        "accessibility_loss_count": total_loss,
        "accessibility_loss_ratio": round((total_loss / scheduled_count), 4) if scheduled_count else 0.0,
        "high_confidence_count": high_confidence_count,
        "at_risk_or_critical_count": critical_or_risky,
        "max_minutes": max_minutes,
    }


def annotate_reachability_window(
    stops: list[dict[str, object]],
    *,
    max_minutes: int,
) -> list[dict[str, object]]:
    annotated: list[dict[str, object]] = []
    for row in stops:
        travel_time_min = int(row.get("travel_time_min") or 0)
        p95_delay_sec = row.get("risk_p95_delay_sec")
        robust_delay_min = max(0.0, int(p95_delay_sec) / 60.0) if isinstance(p95_delay_sec, int) else 0.0
        robust_travel_time_min = round(travel_time_min + robust_delay_min, 2)
        scheduled_accessible = travel_time_min <= max_minutes
        robust_accessible = robust_travel_time_min <= max_minutes
        accessibility_loss_min = round(max(0.0, robust_travel_time_min - travel_time_min), 2)
        annotated.append(
            {
                **row,
                "scheduled_travel_time_min": travel_time_min,
                "robust_travel_time_min": robust_travel_time_min,
                "scheduled_accessible": scheduled_accessible,
                "robust_accessible": robust_accessible,
                "accessibility_loss_flag": scheduled_accessible and not robust_accessible,
                "accessibility_loss_min": accessibility_loss_min,
            }
        )
    return annotated


def stored_reachability_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows = payload.get("all_reachable_stops")
    if isinstance(rows, list):
        return rows
    legacy_rows = payload.get("reachable_stops")
    if isinstance(legacy_rows, list):
        return legacy_rows
    return []


def quality_rank(band: str) -> int:
    return {
        "leading": 5,
        "stable": 4,
        "watchlist": 3,
        "at-risk": 2,
        "critical": 1,
        "unknown": 0,
    }.get(band, 0)


def apply_result_controls(
    stops: list[dict[str, object]],
    *,
    sort_by: str,
    reliability_filter: str,
    bucket_filter: str,
    direct_only: bool,
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for row in stops:
        band = str(row.get("reliability_band", "unknown"))
        if reliability_filter not in {"", "all"} and band != reliability_filter:
            continue
        row_bucket = bucket_label(int(row["travel_time_min"]))
        if bucket_filter not in {"", "all"} and row_bucket != bucket_filter:
            continue
        if direct_only and int(row.get("changes") or 0) != 0:
            continue
        filtered.append(row)

    def _p95(row: dict[str, object]) -> int:
        value = row.get("risk_p95_delay_sec")
        return int(value) if isinstance(value, int) else 999999

    def _changes(row: dict[str, object]) -> int:
        value = row.get("changes")
        return int(value) if isinstance(value, int) else 99

    def _travel(row: dict[str, object]) -> int:
        return int(row["travel_time_min"])

    if sort_by == "travel_time_asc":
        filtered.sort(key=lambda row: (_travel(row), _changes(row), -quality_rank(str(row.get("reliability_band", "unknown"))), _p95(row), str(row.get("name", ""))))
    elif sort_by == "changes_asc":
        filtered.sort(key=lambda row: (_changes(row), _travel(row), -quality_rank(str(row.get("reliability_band", "unknown"))), _p95(row), str(row.get("name", ""))))
    elif sort_by == "quality_asc":
        filtered.sort(key=lambda row: (quality_rank(str(row.get("reliability_band", "unknown"))), -1 * (_p95(row) if _p95(row) != 999999 else -1), _changes(row), _travel(row), str(row.get("name", ""))))
    else:
        filtered.sort(key=lambda row: (-quality_rank(str(row.get("reliability_band", "unknown"))), _p95(row), _changes(row), _travel(row), str(row.get("name", ""))))
    return filtered


def paginate_reachability_results(
    stops: list[dict[str, object]],
    *,
    page: int,
    per_page: int,
    max_result_window: int,
) -> dict[str, object]:
    total_filtered_count = len(stops)
    clipped = stops[:max_result_window]
    total_clipped_count = len(clipped)
    total_pages = max(1, (total_clipped_count + per_page - 1) // per_page)
    safe_page = min(max(1, page), total_pages)
    start = (safe_page - 1) * per_page
    end = start + per_page
    page_rows = clipped[start:end]
    bucket_counts = {"0-15": 0, "16-30": 0, "31-45": 0, "46+": 0}
    for row in clipped:
        bucket_counts[bucket_label(int(row["travel_time_min"]))] += 1
    return {
        "map_stops": clipped,
        "reachable_stops": page_rows,
        "stats": {
            "total_reachable_stop_count": total_filtered_count,
            "clipped_reachable_stop_count": total_clipped_count,
            "returned_stop_count": len(page_rows),
            "page": safe_page,
            "per_page": per_page,
            "total_pages": total_pages,
            "max_result_window": max_result_window,
            "bucket_counts": bucket_counts,
        },
    }


def filter_overlays_to_bounds(
    overlays: dict[str, list[dict[str, object]]],
    *,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> dict[str, list[dict[str, object]]]:
    def _inside(item: dict[str, object]) -> bool:
        lat = item.get("lat")
        lon = item.get("lon")
        if not isinstance(lat, float) or not isinstance(lon, float):
            return False
        return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon

    return {
        "hubs": [item for item in overlays.get("hubs", []) if _inside(item)],
        "vulnerable_nodes": [item for item in overlays.get("vulnerable_nodes", []) if _inside(item)],
    }


class AccessibilityHandler(BaseHTTPRequestHandler):
    service: AccessibilityService
    static_dir: Path

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(self.static_dir / "index.html")
            return
        if parsed.path in {"/app.js", "/styles.css"}:
            self._send_file(self.static_dir / parsed.path.lstrip("/"))
            return
        if parsed.path == "/api/health":
            self._send_json(self.service.health())
            return
        if parsed.path == "/api/frontend-config":
            self._send_json(self.service.frontend_bootstrap())
            return
        if parsed.path == "/api/station-overlays":
            self._send_json(self.service.station_overlay_payload())
            return
        if parsed.path == "/api/location-search":
            params = parse_qs(parsed.query)
            query = (params.get("q") or [""])[0].strip()
            limit = int((params.get("limit") or [str(self.service.cfg.api.location_search_limit)])[0] or 8)
            if not query:
                self._send_json({"error": "q is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                payload = self.service.handle_location_search(query=query, limit=max(1, min(limit, 12)))
                self._send_json(payload)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/reachability":
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            response = self.service.handle_reachability(payload)
            self._send_json(response)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists():
            self._send_json({"error": "static file not found"}, status=HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") or content_type == "application/javascript" else content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Accessibility product proxy server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the accessibility API proxy and static frontend")
    serve.add_argument("--config", default="configs/accessibility.defaults.toml")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    build_static = subparsers.add_parser("build-static", help="Validate static frontend assets")
    build_static.add_argument("--out-dir", default="web/accessibility")
    return parser


def run_server(cfg_path: Path, host: str, port: int) -> int:
    cfg = load_accessibility_config(cfg_path)
    service = AccessibilityService(cfg)
    handler_cls = type("ConfiguredAccessibilityHandler", (AccessibilityHandler,), {})
    handler_cls.service = service
    handler_cls.static_dir = cfg.static_dir

    with ThreadingHTTPServer((host, port), handler_cls) as httpd:
        print(f"accessibility server listening on http://{host}:{port}")
        httpd.serve_forever()
    return 0


def validate_static_assets(out_dir: Path) -> int:
    expected = [
        out_dir / "index.html",
        out_dir / "app.js",
        out_dir / "styles.css",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise SystemExit(f"missing static assets: {', '.join(missing)}")
    print(f"accessibility frontend assets ready in {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return run_server(Path(args.config).resolve(), args.host, args.port)
    if args.command == "build-static":
        return validate_static_assets(Path(args.out_dir).resolve())
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
