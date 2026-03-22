from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from src.accessibility.cache import JsonCache, ReachabilityQuery, build_reachability_cache_key
from src.accessibility.rejseplanen_client import OriginRef, RejseplanenClient, RejseplanenAPIConfig
from src.common.io import ensure_parent, utc_now_iso, write_json


CATEGORY_META = {
    "campus": {"label": "Campuses", "unit": "campuses"},
    "hospital": {"label": "Hospitals", "unit": "hospitals"},
    "job_hub": {"label": "Job Hubs", "unit": "job hubs"},
}


@dataclass(frozen=True)
class AtlasOrigin:
    origin_id: str
    name: str
    lat: float
    lon: float
    origin_stop_id: str
    origin_stop_name: str
    origin_stop_lat: float | None
    origin_stop_lon: float | None
    municipality: str
    neighborhood: str
    population_weight: float
    cell_size_m: int
    active: bool


@dataclass(frozen=True)
class AtlasPoi:
    poi_id: str
    name: str
    category: str
    lat: float
    lon: float
    weight: float
    nearest_stop_id: str
    candidate_stop_ids: tuple[str, ...]


@dataclass(frozen=True)
class AtlasScenario:
    scenario_id: str
    label: str
    depart_at_local: str
    short_label: str
    description: str


@dataclass(frozen=True)
class AtlasBuildConfig:
    source_mode: str
    title: str
    subtitle: str
    operational_boundary_label: str
    origins_path: Path
    pois_path: Path
    scenarios_path: Path
    output_dir: Path
    durations: tuple[int, ...]
    max_changes_options: tuple[int, ...]
    default_duration: int
    default_category: str
    default_scenario_id: str
    default_max_changes: int
    map_center_lat: float
    map_center_lon: float
    map_zoom: int
    polygon_half_size_m: int
    modes: tuple[str, ...]


@dataclass(frozen=True)
class Opportunity:
    origin_id: str
    poi_id: str
    scenario_id: str
    max_changes: int
    travel_time_min: int
    changes: int
    source: str


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _split_pipe_list(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split("|") if part.strip())


def load_origins(path: Path, default_cell_size_m: int) -> list[AtlasOrigin]:
    origins: list[AtlasOrigin] = []
    for row in _load_csv_rows(path):
        origins.append(
            AtlasOrigin(
                origin_id=str(row["origin_id"]).strip(),
                name=str(row["name"]).strip(),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                origin_stop_id=str(row.get("origin_stop_id", "")).strip(),
                origin_stop_name=str(row.get("origin_stop_name", "")).strip(),
                origin_stop_lat=float(row["origin_stop_lat"]) if row.get("origin_stop_lat") else None,
                origin_stop_lon=float(row["origin_stop_lon"]) if row.get("origin_stop_lon") else None,
                municipality=str(row.get("municipality", "")).strip(),
                neighborhood=str(row.get("neighborhood", "")).strip(),
                population_weight=float(row.get("population_weight", 1.0) or 1.0),
                cell_size_m=int(row.get("cell_size_m", default_cell_size_m) or default_cell_size_m),
                active=str(row.get("is_active", "true")).strip().lower() not in {"0", "false", "no"},
            )
        )
    return [origin for origin in origins if origin.active]


def load_pois(path: Path) -> list[AtlasPoi]:
    pois: list[AtlasPoi] = []
    for row in _load_csv_rows(path):
        category = str(row["category"]).strip()
        if category not in CATEGORY_META:
            raise ValueError(f"Unsupported POI category: {category}")
        nearest_stop_id = str(row.get("nearest_stop_id", "")).strip()
        candidate_stop_ids = _split_pipe_list(str(row.get("candidate_stop_ids", "")).strip())
        if not candidate_stop_ids and nearest_stop_id:
            candidate_stop_ids = (nearest_stop_id,)
        pois.append(
            AtlasPoi(
                poi_id=str(row["poi_id"]).strip(),
                name=str(row["name"]).strip(),
                category=category,
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                weight=float(row.get("weight", 1.0) or 1.0),
                nearest_stop_id=nearest_stop_id,
                candidate_stop_ids=candidate_stop_ids,
            )
        )
    return pois


def load_scenarios(path: Path) -> list[AtlasScenario]:
    scenarios: list[AtlasScenario] = []
    for row in _load_csv_rows(path):
        scenarios.append(
            AtlasScenario(
                scenario_id=str(row["scenario_id"]).strip(),
                label=str(row["label"]).strip(),
                depart_at_local=str(row["depart_at_local"]).strip(),
                short_label=str(row.get("short_label", row["label"])).strip(),
                description=str(row.get("description", "")).strip(),
            )
        )
    return scenarios


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return radius_km * (2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))


def _sample_scenario_penalty(scenario_id: str) -> int:
    return {
        "weekday_am": 5,
        "weekday_midday": 0,
        "weekday_pm": 6,
        "saturday_noon": 3,
    }.get(scenario_id, 2)


def _sample_category_penalty(category: str) -> int:
    return {"campus": 0, "hospital": 3, "job_hub": -1}.get(category, 0)


def _estimated_changes(distance_km: float) -> int:
    if distance_km <= 5:
        return 0
    if distance_km <= 18:
        return 1
    return 2


def _sample_travel_time(origin: AtlasOrigin, poi: AtlasPoi, scenario: AtlasScenario, max_changes: int) -> Opportunity | None:
    distance_km = _haversine_km(origin.lat, origin.lon, poi.lat, poi.lon)
    changes = _estimated_changes(distance_km)
    if changes > max_changes:
        return None
    suburban_penalty = 3 if origin.municipality != "Copenhagen" and poi.category == "job_hub" else 0
    long_tail_penalty = 4 if origin.municipality != "Copenhagen" and distance_km > 14 else 0
    max_change_penalty = 2 if max_changes == 1 and changes == 1 else 0
    travel_time = (
        8
        + int(round(distance_km * 3.9))
        + _sample_scenario_penalty(scenario.scenario_id)
        + _sample_category_penalty(poi.category)
        + suburban_penalty
        + long_tail_penalty
        + max_change_penalty
    )
    return Opportunity(
        origin_id=origin.origin_id,
        poi_id=poi.poi_id,
        scenario_id=scenario.scenario_id,
        max_changes=max_changes,
        travel_time_min=max(8, travel_time),
        changes=changes,
        source="sample",
    )


def _origin_access_penalty_minutes(origin: AtlasOrigin) -> int:
    if origin.origin_stop_lat is None or origin.origin_stop_lon is None:
        return 0
    walk_km = _haversine_km(origin.lat, origin.lon, origin.origin_stop_lat, origin.origin_stop_lon)
    return max(0, min(18, int(round(walk_km * 12.5))))


def generate_sample_opportunities(
    origins: list[AtlasOrigin],
    pois: list[AtlasPoi],
    scenarios: list[AtlasScenario],
    max_changes_options: tuple[int, ...],
) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    for origin in origins:
        for scenario in scenarios:
            for max_changes in max_changes_options:
                for poi in pois:
                    item = _sample_travel_time(origin, poi, scenario, max_changes)
                    if item is not None:
                        opportunities.append(item)
    return opportunities


def generate_live_opportunities(
    *,
    build_cfg: AtlasBuildConfig,
    api_cfg: RejseplanenAPIConfig,
    cache: JsonCache,
    cache_bucket_minutes: int,
    origins: list[AtlasOrigin],
    pois: list[AtlasPoi],
    scenarios: list[AtlasScenario],
) -> tuple[list[Opportunity], dict[str, int]]:
    client = RejseplanenClient(api_cfg)
    max_duration = max(build_cfg.durations)
    opportunity_rows: list[Opportunity] = []
    stats = {"queries": 0, "cache_hits": 0, "logical_slices": 0}

    poi_by_stop: dict[str, list[AtlasPoi]] = defaultdict(list)
    for poi in pois:
        for stop_id in poi.candidate_stop_ids:
            poi_by_stop[stop_id].append(poi)

    for origin in origins:
        origin_ref = OriginRef(
            id=origin.origin_stop_id,
            type="stop" if origin.origin_stop_id else "coord",
            lat=None if origin.origin_stop_id else origin.lat,
            lon=None if origin.origin_stop_id else origin.lon,
        )
        for scenario in scenarios:
            for max_changes in build_cfg.max_changes_options:
                query = ReachabilityQuery(
                    origin_key=origin.origin_stop_id or origin.origin_id,
                    depart_at_local=scenario.depart_at_local,
                    max_minutes=max_duration,
                    modes=build_cfg.modes,
                    max_changes=max_changes,
                )
                stats["logical_slices"] += 1
                cache_key = build_reachability_cache_key(
                    query,
                    bucket_minutes=cache_bucket_minutes,
                    version="atlas-v1",
                )
                cached = cache.get(cache_key, ttl_sec=60 * 60 * 24 * 14)
                if cached is not None:
                    stop_rows = list(cached.payload.get("reachable_stops", []))
                    stats["cache_hits"] += 1
                else:
                    response = client.reachability_search(origin=origin_ref, query=query)
                    stop_rows = response.normalized_items
                    cache.set(cache_key, {"reachable_stops": stop_rows, "request_url": response.request_url})
                    stats["queries"] += 1

                best_by_poi: dict[str, Opportunity] = {}
                origin_access_penalty = _origin_access_penalty_minutes(origin)
                for stop in stop_rows:
                    stop_id = str(stop.get("id", "")).strip()
                    if not stop_id:
                        continue
                    travel_time = int(stop.get("travel_time_min") or 0) + origin_access_penalty
                    changes = int(stop.get("changes") or 0)
                    for poi in poi_by_stop.get(stop_id, []):
                        current = best_by_poi.get(poi.poi_id)
                        candidate = Opportunity(
                            origin_id=origin.origin_id,
                            poi_id=poi.poi_id,
                            scenario_id=scenario.scenario_id,
                            max_changes=max_changes,
                            travel_time_min=travel_time,
                            changes=changes,
                            source="api",
                        )
                        if current is None or candidate.travel_time_min < current.travel_time_min:
                            best_by_poi[poi.poi_id] = candidate
                opportunity_rows.extend(best_by_poi.values())

    return opportunity_rows, stats


def _deg_offsets(lat: float, half_size_m: int) -> tuple[float, float]:
    lat_delta = half_size_m / 111_320.0
    lon_delta = half_size_m / (111_320.0 * max(math.cos(math.radians(lat)), 0.2))
    return lat_delta, lon_delta


def _square_polygon(lat: float, lon: float, half_size_m: int) -> list[list[list[float]]]:
    lat_delta, lon_delta = _deg_offsets(lat, half_size_m)
    return [[
        [lon - lon_delta, lat - lat_delta],
        [lon + lon_delta, lat - lat_delta],
        [lon + lon_delta, lat + lat_delta],
        [lon - lon_delta, lat + lat_delta],
        [lon - lon_delta, lat - lat_delta],
    ]]


def _combo_key(scenario_id: str, duration: int, max_changes: int) -> str:
    return f"{scenario_id}__{duration}__mc{max_changes}"


def _origin_detail_path(output_dir: Path, origin_id: str) -> Path:
    return output_dir / "origins" / f"{origin_id}.json"


def _layer_path(output_dir: Path, combo_key: str) -> Path:
    return output_dir / "layers" / f"{combo_key}.geojson"


def _empty_category_metrics() -> dict[str, Any]:
    return {
        "count": 0,
        "weighted_score": 0.0,
        "nearest_time_min": None,
        "delta_vs_median": 0.0,
        "percentile": 0.0,
    }


def build_atlas_bundle(
    *,
    build_cfg: AtlasBuildConfig,
    opportunities: list[Opportunity],
    origins: list[AtlasOrigin],
    pois: list[AtlasPoi],
    scenarios: list[AtlasScenario],
    query_stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    output_dir = build_cfg.output_dir
    ensure_parent(output_dir / ".keep")

    poi_lookup = {poi.poi_id: poi for poi in pois}
    scenario_lookup = {scenario.scenario_id: scenario for scenario in scenarios}

    metrics_by_origin_combo: dict[tuple[str, str, int], dict[str, list[Opportunity]]] = defaultdict(lambda: defaultdict(list))
    for item in opportunities:
        metrics_by_origin_combo[(item.origin_id, item.scenario_id, item.max_changes)][poi_lookup[item.poi_id].category].append(item)

    detail_payload_index: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for origin in origins:
        for scenario in scenarios:
            for max_changes in build_cfg.max_changes_options:
                category_rows = metrics_by_origin_combo[(origin.origin_id, scenario.scenario_id, max_changes)]
                combo_entry = {
                    "scenario_id": scenario.scenario_id,
                    "scenario_label": scenario.label,
                    "depart_at_local": scenario.depart_at_local,
                    "max_changes": max_changes,
                    "metrics_by_duration": {},
                    "poi_opportunities": [],
                }
                for duration in build_cfg.durations:
                    duration_metrics: dict[str, Any] = {}
                    for category in CATEGORY_META:
                        reachable = [
                            item
                            for item in category_rows.get(category, [])
                            if item.travel_time_min <= duration and item.changes <= max_changes
                        ]
                        nearest = min((item.travel_time_min for item in reachable), default=None)
                        duration_metrics[category] = {
                            "count": len(reachable),
                            "weighted_score": round(sum(poi_lookup[item.poi_id].weight for item in reachable), 2),
                            "nearest_time_min": nearest,
                        }
                    combo_entry["metrics_by_duration"][str(duration)] = duration_metrics

                all_poi_rows = []
                for category in CATEGORY_META:
                    for item in sorted(category_rows.get(category, []), key=lambda row: (row.travel_time_min, row.poi_id)):
                        poi = poi_lookup[item.poi_id]
                        all_poi_rows.append(
                            {
                                "poi_id": poi.poi_id,
                                "name": poi.name,
                                "category": poi.category,
                                "category_label": CATEGORY_META[poi.category]["label"],
                                "weight": poi.weight,
                                "lat": poi.lat,
                                "lon": poi.lon,
                                "travel_time_min": item.travel_time_min,
                                "changes": item.changes,
                                "source": item.source,
                            }
                        )
                combo_entry["poi_opportunities"] = all_poi_rows
                detail_payload_index[origin.origin_id].append(combo_entry)

    layer_manifest: list[dict[str, Any]] = []
    for scenario in scenarios:
        for duration in build_cfg.durations:
            for max_changes in build_cfg.max_changes_options:
                category_score_vectors: dict[str, list[float]] = defaultdict(list)
                feature_metrics: dict[str, dict[str, Any]] = {}
                for origin in origins:
                    combo = next(
                        item
                        for item in detail_payload_index[origin.origin_id]
                        if item["scenario_id"] == scenario.scenario_id and item["max_changes"] == max_changes
                    )
                    metrics_for_duration = combo["metrics_by_duration"][str(duration)]
                    feature_metrics[origin.origin_id] = metrics_for_duration
                    for category, values in metrics_for_duration.items():
                        category_score_vectors[category].append(float(values["weighted_score"]))

                medians = {
                    category: round(median(values), 2) if values else 0.0
                    for category, values in category_score_vectors.items()
                }
                overall_avgs = {
                    category: round(sum(values) / len(values), 2) if values else 0.0
                    for category, values in category_score_vectors.items()
                }

                for origin in origins:
                    metrics_for_duration = feature_metrics[origin.origin_id]
                    for category in CATEGORY_META:
                        score = float(metrics_for_duration[category]["weighted_score"])
                        scores = sorted(category_score_vectors[category])
                        rank = sum(1 for current in scores if current <= score)
                        percentile = round((rank / len(scores)) * 100.0, 1) if scores else 0.0
                        metrics_for_duration[category]["delta_vs_median"] = round(score - medians[category], 2)
                        metrics_for_duration[category]["percentile"] = percentile

                municipality_bucket: dict[str, dict[str, Any]] = {}
                for origin in origins:
                    municipality_entry = municipality_bucket.setdefault(
                        origin.municipality,
                        {
                            "municipality": origin.municipality,
                            "origin_count": 0,
                            "population_weight_sum": 0.0,
                            "category_metrics": {
                                category: {
                                    "weighted_score_total": 0.0,
                                    "count_total": 0.0,
                                    "nearest_time_weighted_total": 0.0,
                                    "nearest_time_weight": 0.0,
                                    "best_score": 0.0,
                                }
                                for category in CATEGORY_META
                            },
                        },
                    )
                    municipality_entry["origin_count"] += 1
                    municipality_entry["population_weight_sum"] += origin.population_weight
                    metrics_for_duration = feature_metrics[origin.origin_id]
                    for category in CATEGORY_META:
                        category_entry = municipality_entry["category_metrics"][category]
                        weight = origin.population_weight
                        category_entry["weighted_score_total"] += float(metrics_for_duration[category]["weighted_score"]) * weight
                        category_entry["count_total"] += float(metrics_for_duration[category]["count"]) * weight
                        nearest_time = metrics_for_duration[category]["nearest_time_min"]
                        if isinstance(nearest_time, int):
                            category_entry["nearest_time_weighted_total"] += nearest_time * weight
                            category_entry["nearest_time_weight"] += weight
                        category_entry["best_score"] = max(
                            category_entry["best_score"],
                            float(metrics_for_duration[category]["weighted_score"]),
                        )

                municipality_summary: list[dict[str, Any]] = []
                category_rankings: dict[str, list[tuple[str, float]]] = {}
                for category in CATEGORY_META:
                    category_rankings[category] = sorted(
                        [
                            (
                                municipality_name,
                                (
                                    stats["category_metrics"][category]["weighted_score_total"]
                                    / max(stats["population_weight_sum"], 1e-9)
                                ),
                            )
                            for municipality_name, stats in municipality_bucket.items()
                        ],
                        key=lambda item: (-item[1], item[0]),
                    )

                for municipality_name, stats in municipality_bucket.items():
                    population_weight_sum = max(float(stats["population_weight_sum"]), 1e-9)
                    category_metrics_out: dict[str, Any] = {}
                    for category in CATEGORY_META:
                        category_entry = stats["category_metrics"][category]
                        avg_weighted_score = category_entry["weighted_score_total"] / population_weight_sum
                        avg_count = category_entry["count_total"] / population_weight_sum
                        nearest_weight = category_entry["nearest_time_weight"]
                        avg_nearest = (
                            round(category_entry["nearest_time_weighted_total"] / nearest_weight, 1)
                            if nearest_weight > 0
                            else None
                        )
                        ranking = category_rankings[category]
                        rank = next(
                            index
                            for index, (name, _) in enumerate(ranking, start=1)
                            if name == municipality_name
                        )
                        category_metrics_out[category] = {
                            "avg_weighted_score": round(avg_weighted_score, 2),
                            "avg_count": round(avg_count, 2),
                            "avg_nearest_time_min": avg_nearest,
                            "best_score": round(float(category_entry["best_score"]), 2),
                            "delta_vs_overall_avg": round(avg_weighted_score - overall_avgs[category], 2),
                            "rank": rank,
                            "municipality_count": len(ranking),
                        }

                    municipality_summary.append(
                        {
                            "municipality": municipality_name,
                            "origin_count": int(stats["origin_count"]),
                            "population_weight_sum": round(float(stats["population_weight_sum"]), 2),
                            "category_metrics": category_metrics_out,
                        }
                    )

                municipality_summary.sort(key=lambda item: item["municipality"])

                features = []
                for origin in origins:
                    metrics_for_duration = feature_metrics[origin.origin_id]
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": _square_polygon(
                                    origin.lat,
                                    origin.lon,
                                    origin.cell_size_m or build_cfg.polygon_half_size_m,
                                ),
                            },
                            "properties": {
                                "origin_id": origin.origin_id,
                                "name": origin.name,
                                "municipality": origin.municipality,
                                "neighborhood": origin.neighborhood,
                                "population_weight": origin.population_weight,
                                "centroid": {"lat": origin.lat, "lon": origin.lon},
                                "scenario_id": scenario.scenario_id,
                                "duration": duration,
                                "max_changes": max_changes,
                                "category_metrics": metrics_for_duration,
                            },
                        }
                    )
                combo_name = _combo_key(scenario.scenario_id, duration, max_changes)
                write_json(
                    _layer_path(output_dir, combo_name),
                    {
                        "type": "FeatureCollection",
                        "generated_at_utc": generated_at,
                        "scenario": {
                            "scenario_id": scenario.scenario_id,
                            "label": scenario.label,
                            "depart_at_local": scenario.depart_at_local,
                        },
                        "duration": duration,
                        "max_changes": max_changes,
                        "medians": medians,
                        "overall_avgs": overall_avgs,
                        "municipality_summary": municipality_summary,
                        "features": features,
                    },
                )
                layer_manifest.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "duration": duration,
                        "max_changes": max_changes,
                        "path": f"./data/layers/{combo_name}.geojson",
                    }
                )

    for origin in origins:
        write_json(
            _origin_detail_path(output_dir, origin.origin_id),
            {
                "generated_at_utc": generated_at,
                "origin": {
                    "origin_id": origin.origin_id,
                    "name": origin.name,
                    "lat": origin.lat,
                    "lon": origin.lon,
                    "origin_stop_id": origin.origin_stop_id,
                    "origin_stop_name": origin.origin_stop_name,
                    "origin_stop_lat": origin.origin_stop_lat,
                    "origin_stop_lon": origin.origin_stop_lon,
                    "municipality": origin.municipality,
                    "neighborhood": origin.neighborhood,
                    "population_weight": origin.population_weight,
                },
                "combinations": detail_payload_index[origin.origin_id],
            },
        )

    bootstrap = {
        "generated_at_utc": generated_at,
        "title": build_cfg.title,
        "subtitle": build_cfg.subtitle,
        "operational_boundary_label": build_cfg.operational_boundary_label,
        "source_mode": build_cfg.source_mode,
        "defaults": {
            "category": build_cfg.default_category,
            "scenario_id": build_cfg.default_scenario_id,
            "duration": build_cfg.default_duration,
            "max_changes": build_cfg.default_max_changes,
        },
        "durations": list(build_cfg.durations),
        "max_changes_options": list(build_cfg.max_changes_options),
        "categories": [
            {"category": key, "label": value["label"], "unit": value["unit"]}
            for key, value in CATEGORY_META.items()
        ],
        "scenarios": [
            {
                "scenario_id": scenario.scenario_id,
                "label": scenario.label,
                "short_label": scenario.short_label,
                "description": scenario.description,
                "depart_at_local": scenario.depart_at_local,
            }
            for scenario in scenarios
        ],
        "map": {
            "center": [build_cfg.map_center_lat, build_cfg.map_center_lon],
            "zoom": build_cfg.map_zoom,
        },
        "origins": [
            {
                "origin_id": origin.origin_id,
                "name": origin.name,
                "origin_stop_id": origin.origin_stop_id,
                "origin_stop_name": origin.origin_stop_name,
                "municipality": origin.municipality,
                "neighborhood": origin.neighborhood,
                "detail_path": f"./data/origins/{origin.origin_id}.json",
            }
            for origin in origins
        ],
        "pois": [
            {
                "poi_id": poi.poi_id,
                "name": poi.name,
                "category": poi.category,
                "weight": poi.weight,
                "lat": poi.lat,
                "lon": poi.lon,
            }
            for poi in pois
        ],
        "files": {
            "layers": layer_manifest,
            "detail_template": "./data/origins/{origin_id}.json",
        },
        "query_stats": query_stats or {},
    }
    write_json(output_dir / "atlas_bootstrap.json", bootstrap)
    return {
        "generated_at_utc": generated_at,
        "origin_count": len(origins),
        "poi_count": len(pois),
        "scenario_count": len(scenarios),
        "layer_count": len(layer_manifest),
        "source_mode": build_cfg.source_mode,
        "query_stats": query_stats or {},
    }
