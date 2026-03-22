from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

from src.accessibility.atlas import (
    AtlasBuildConfig,
    build_atlas_bundle,
    generate_live_opportunities,
    generate_sample_opportunities,
    load_origins,
    load_pois,
    load_scenarios,
)
from src.accessibility.cache import JsonCache
from src.accessibility.rejseplanen_client import RejseplanenAPIConfig
from src.common.io import utc_now_iso


@dataclass(frozen=True)
class CacheConfig:
    root_dir: Path
    reachability_bucket_minutes: int


@dataclass(frozen=True)
class AccessibilityConfig:
    timezone: str
    static_dir: Path
    cache: CacheConfig
    api: RejseplanenAPIConfig
    atlas: AtlasBuildConfig


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
        try:
            return float(value)
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
    atlas_section = raw.get("atlas", {})
    if not isinstance(cache_section, dict) or not isinstance(api_section, dict) or not isinstance(atlas_section, dict):
        raise ValueError("cache, api, and atlas sections are required")

    return AccessibilityConfig(
        timezone=str(raw.get("timezone", "Europe/Copenhagen")),
        static_dir=(root / str(raw.get("static_dir", "web/accessibility"))).resolve(),
        cache=CacheConfig(
            root_dir=(root / str(cache_section.get("root_dir", "data/cache/accessibility"))).resolve(),
            reachability_bucket_minutes=int(cache_section.get("reachability_bucket_minutes", 5)),
        ),
        api=RejseplanenAPIConfig(
            base_url=str(api_section.get("base_url", "https://www.rejseplanen.dk/api")),
            request_timeout_sec=int(api_section.get("request_timeout_sec", 15)),
            location_search_limit=int(api_section.get("location_search_limit", 8)),
            max_minutes_default=int(api_section.get("max_minutes_default", 60)),
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
            reachability_forward_param=str(api_section.get("reachability_forward_param", "forward")),
            reachability_forward_default=int(api_section.get("reachability_forward_default", 1)),
            reachability_filter_end_walks_param=str(
                api_section.get("reachability_filter_end_walks_param", "filterEndWalks")
            ),
            reachability_filter_end_walks_default=int(
                api_section.get("reachability_filter_end_walks_default", 1)
            ),
            reachability_modes_param=str(api_section.get("reachability_modes_param", "products")),
            mode_separator=str(api_section.get("mode_separator", ",")),
        ),
        atlas=AtlasBuildConfig(
            source_mode=str(atlas_section.get("source_mode", "sample")),
            title=str(atlas_section.get("title", "Copenhagen Mobility Resilience Atlas")),
            subtitle=str(
                atlas_section.get(
                    "subtitle",
                    "A fixed-scenario public-transit atlas for seeing which neighborhoods keep access to campuses, hospitals, and job hubs when time budgets and transfer caps get real",
                )
            ),
            operational_boundary_label=str(
                atlas_section.get("operational_boundary_label", "Greater Copenhagen operational boundary, Denmark side only")
            ),
            origins_path=(root / str(atlas_section.get("origins_path", "configs/atlas.origins.sample.csv"))).resolve(),
            pois_path=(root / str(atlas_section.get("pois_path", "configs/atlas.pois.sample.csv"))).resolve(),
            scenarios_path=(root / str(atlas_section.get("scenarios_path", "configs/atlas.scenarios.sample.csv"))).resolve(),
            output_dir=(root / str(atlas_section.get("output_dir", "web/accessibility/data"))).resolve(),
            durations=tuple(int(value) for value in atlas_section.get("durations", [30, 45, 60])),
            max_changes_options=tuple(int(value) for value in atlas_section.get("max_changes_options", [1, 2])),
            default_duration=int(atlas_section.get("default_duration", 45)),
            default_category=str(atlas_section.get("default_category", "job_hub")),
            default_scenario_id=str(atlas_section.get("default_scenario_id", "weekday_am")),
            default_max_changes=int(atlas_section.get("default_max_changes", 2)),
            map_center_lat=float(atlas_section.get("map_center_lat", 55.6761)),
            map_center_lon=float(atlas_section.get("map_center_lon", 12.5683)),
            map_zoom=int(atlas_section.get("map_zoom", 10)),
            polygon_half_size_m=int(atlas_section.get("polygon_half_size_m", 450)),
            modes=tuple(str(value) for value in atlas_section.get("modes", ["train", "metro", "bus"])),
        ),
    )


def build_atlas(cfg_path: Path) -> dict[str, object]:
    cfg = load_accessibility_config(cfg_path)
    origins = load_origins(cfg.atlas.origins_path, cfg.atlas.polygon_half_size_m)
    pois = load_pois(cfg.atlas.pois_path)
    scenarios = load_scenarios(cfg.atlas.scenarios_path)
    query_stats: dict[str, int] = {}

    if cfg.atlas.source_mode == "api":
        opportunities, query_stats = generate_live_opportunities(
            build_cfg=cfg.atlas,
            api_cfg=cfg.api,
            cache=JsonCache(cfg.cache.root_dir),
            cache_bucket_minutes=cfg.cache.reachability_bucket_minutes,
            origins=origins,
            pois=pois,
            scenarios=scenarios,
        )
    else:
        opportunities = generate_sample_opportunities(
            origins=origins,
            pois=pois,
            scenarios=scenarios,
            max_changes_options=cfg.atlas.max_changes_options,
        )

    result = build_atlas_bundle(
        build_cfg=cfg.atlas,
        opportunities=opportunities,
        origins=origins,
        pois=pois,
        scenarios=scenarios,
        query_stats=query_stats,
    )
    return {
        **result,
        "output_dir": str(cfg.atlas.output_dir),
    }


class AccessibilityHandler(BaseHTTPRequestHandler):
    static_dir: Path
    timezone: str

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            atlas_bootstrap = self.static_dir / "data" / "atlas_bootstrap.json"
            self._send_json(
                {
                    "ok": True,
                    "timezone": self.timezone,
                    "static_dir": str(self.static_dir),
                    "atlas_bundle_ready": atlas_bootstrap.exists(),
                    "generated_at_utc": utc_now_iso(),
                }
            )
            return

        relative_path = self.path.split("?", 1)[0]
        if relative_path in {"", "/"}:
            relative_path = "/index.html"
        target = (self.static_dir / relative_path.lstrip("/")).resolve()
        static_root = self.static_dir.resolve()
        if not str(target).startswith(str(static_root)) or not target.exists() or not target.is_file():
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self._send_file(target)

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
        body = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        if content_type.startswith("text/") or content_type == "application/javascript" or content_type.endswith("+json"):
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        else:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Copenhagen mobility resilience atlas server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Serve the public mobility resilience site and atlas bundle")
    serve.add_argument("--config", default="configs/accessibility.defaults.toml")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    build_static = subparsers.add_parser("build-static", help="Validate public site assets and atlas bundle")
    build_static.add_argument("--out-dir", default="web/accessibility")

    build_atlas_parser = subparsers.add_parser("build-atlas", help="Build the precomputed mobility resilience atlas bundle")
    build_atlas_parser.add_argument("--config", default="configs/accessibility.defaults.toml")
    return parser


def run_server(cfg_path: Path, host: str, port: int) -> int:
    cfg = load_accessibility_config(cfg_path)
    handler_cls = type("ConfiguredAccessibilityHandler", (AccessibilityHandler,), {})
    handler_cls.static_dir = cfg.static_dir
    handler_cls.timezone = cfg.timezone
    with ThreadingHTTPServer((host, port), handler_cls) as httpd:
        print(f"mobility resilience atlas listening on http://{host}:{port}")
        httpd.serve_forever()
    return 0


def validate_static_assets(out_dir: Path) -> int:
    expected = [
        out_dir / "index.html",
        out_dir / "landing.css",
        out_dir / "atlas.html",
        out_dir / "benchmark.html",
        out_dir / "results.html",
        out_dir / "app.js",
        out_dir / "styles.css",
        out_dir / "data" / "atlas_bootstrap.json",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise SystemExit(f"missing atlas assets: {', '.join(missing)}")
    print(f"public site assets ready in {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return run_server(Path(args.config).resolve(), args.host, args.port)
    if args.command == "build-static":
        return validate_static_assets(Path(args.out_dir).resolve())
    if args.command == "build-atlas":
        result = build_atlas(Path(args.config).resolve())
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
