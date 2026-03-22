from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

from src.accessibility.rejseplanen_client import RejseplanenAPIConfig, RejseplanenClient


@dataclass(frozen=True)
class Anchor:
    stop_id: str
    station_name: str
    municipality: str
    neighborhood: str
    lat: float
    lon: float


ANCHOR_CONTEXT = {
    "8600626": ("Copenhagen", "Inner City"),
    "8600646": ("Copenhagen", "Norrebro"),
    "8600650": ("Copenhagen", "Osterbro"),
    "8600624": ("Copenhagen", "Valby"),
    "8600736": ("Frederiksberg", "Frederiksberg-West"),
    "8600655": ("Gentofte", "Hellerup"),
    "8600675": ("Lyngby-Taarbaek", "Lyngby"),
    "8600600": ("Hvidovre", "Hvidovre"),
    "8600708": ("Ballerup", "Ballerup"),
    "8600617": ("Roskilde", "Roskilde"),
    "8603327": ("Tarnby", "Airport"),
    "8600856": ("Copenhagen", "Orestad"),
    "8600783": ("Copenhagen", "Kobenhavn Syd"),
    "8600673": ("Gentofte", "Gentofte"),
    "8600654": ("Copenhagen", "Svanemollen"),
    "8600653": ("Copenhagen", "Nordhavn"),
    "8600677": ("Rudersdal", "Holte"),
    "8600683": ("Hillerod", "Hillerod"),
    "8600620": ("Hoje-Taastrup", "Taastrup"),
    "8600622": ("Glostrup", "Glostrup"),
}


OFFSETS_M = [
    ("core", 0, 0, 1.00),
    ("north", 0, 420, 0.95),
    ("northeast", 320, 320, 0.91),
    ("east", 420, 0, 0.93),
    ("southeast", 320, -320, 0.89),
    ("south", 0, -420, 0.94),
    ("southwest", -320, -320, 0.88),
    ("west", -420, 0, 0.93),
    ("northwest", -320, 320, 0.90),
]


def _load_station_seeds(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _slugify(value: str) -> str:
    ascii_text = (
        value.replace("ø", "o")
        .replace("Ø", "O")
        .replace("æ", "ae")
        .replace("Æ", "Ae")
        .replace("å", "aa")
        .replace("Å", "Aa")
    )
    ascii_text = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()
    return ascii_text


def _meters_to_coord(anchor: Anchor, east_m: float, north_m: float) -> tuple[float, float]:
    lat_delta = north_m / 111_320.0
    lon_delta = east_m / (111_320.0 * max(math.cos(math.radians(anchor.lat)), 0.2))
    return anchor.lat + lat_delta, anchor.lon + lon_delta


def _client() -> RejseplanenClient:
    return RejseplanenClient(
        RejseplanenAPIConfig(
            base_url="https://www.rejseplanen.dk/api",
            request_timeout_sec=20,
            location_search_limit=3,
            max_minutes_default=60,
            max_changes_default=2,
            access_id_env="REJSEPLANEN_API_KEY",
            access_id_query_param="accessId",
            format_param="format",
            format_value="json",
            location_search_path="location.name",
            location_search_query_param="input",
            location_search_limit_param="maxNo",
            reachability_path="reachability",
            reachability_origin_id_param="originId",
            reachability_origin_lat_param="originCoordLat",
            reachability_origin_lon_param="originCoordLong",
            reachability_date_param="date",
            reachability_time_param="time",
            reachability_duration_param="duration",
            reachability_max_changes_param="maxChange",
            reachability_forward_param="forward",
            reachability_forward_default=1,
            reachability_filter_end_walks_param="filterEndWalks",
            reachability_filter_end_walks_default=1,
            reachability_modes_param="products",
            mode_separator=",",
        )
    )


def _fetch_anchor(client: RejseplanenClient, station_id: str, fallback_name: str) -> Anchor:
    response = client.location_search(query=station_id, limit=3)
    for item in response.normalized_items:
        if str(item.get("id", "")).strip() == station_id:
            municipality, neighborhood = ANCHOR_CONTEXT.get(station_id, ("Greater Copenhagen", fallback_name))
            return Anchor(
                stop_id=station_id,
                station_name=str(item.get("name", fallback_name)).strip(),
                municipality=municipality,
                neighborhood=neighborhood,
                lat=float(item["lat"]),
                lon=float(item["lon"]),
            )
    raise RuntimeError(f"Could not resolve anchor stop {station_id}")


def generate_origins(seed_path: Path, output_path: Path) -> int:
    seeds = _load_station_seeds(seed_path)
    client = _client()
    anchors = [
        _fetch_anchor(client, str(row["api_station_id"]).strip(), str(row["station_name"]).strip())
        for row in seeds
    ]

    rows: list[dict[str, object]] = []
    for anchor in anchors:
        base_slug = _slugify(anchor.station_name)
        for suffix, east_m, north_m, weight in OFFSETS_M:
            lat, lon = _meters_to_coord(anchor, east_m, north_m)
            rows.append(
                {
                    "origin_id": f"{base_slug}_{suffix}",
                    "name": f"{anchor.station_name} {suffix.replace('_', ' ')} catchment",
                    "lat": f"{lat:.6f}",
                    "lon": f"{lon:.6f}",
                    "origin_stop_id": anchor.stop_id,
                    "origin_stop_name": anchor.station_name,
                    "origin_stop_lat": f"{anchor.lat:.6f}",
                    "origin_stop_lon": f"{anchor.lon:.6f}",
                    "municipality": anchor.municipality,
                    "neighborhood": anchor.neighborhood,
                    "population_weight": f"{weight:.2f}",
                    "cell_size_m": "360",
                    "is_active": "true",
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "origin_id",
                "name",
                "lat",
                "lon",
                "origin_stop_id",
                "origin_stop_name",
                "origin_stop_lat",
                "origin_stop_lon",
                "municipality",
                "neighborhood",
                "population_weight",
                "cell_size_m",
                "is_active",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} origins to {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate expanded atlas origin grid from anchor stations")
    parser.add_argument("--seed", default="configs/stations_seed.csv")
    parser.add_argument("--out", default="configs/atlas.origins.expanded.csv")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return generate_origins(Path(args.seed).resolve(), Path(args.out).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
