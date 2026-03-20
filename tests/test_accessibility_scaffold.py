import unittest
from pathlib import Path

from src.accessibility.cache import JsonCache, ReachabilityQuery, build_reachability_cache_key, build_location_search_cache_key
from src.accessibility.rejseplanen_client import (
    OriginRef,
    RejseplanenAPIConfig,
    _extract_location_id,
    _extract_primary_product,
    _products_mask_for_modes,
    build_location_search_params,
    build_reachability_params,
)
from src.accessibility.server import (
    apply_result_controls,
    build_parser,
    filter_overlays_to_bounds,
    load_accessibility_config,
    paginate_reachability_results,
    summarize_reachability_window,
)
from src.accessibility.transform import load_line_reliability_lookup


class AccessibilityScaffoldTest(unittest.TestCase):
    def test_server_parser_accepts_scaffold_commands(self):
        parser = build_parser()
        serve_args = parser.parse_args(["serve"])
        static_args = parser.parse_args(["build-static"])
        self.assertEqual(serve_args.command, "serve")
        self.assertEqual(static_args.command, "build-static")

    def test_config_loader_reads_accessibility_defaults(self):
        repo_root = Path(__file__).resolve().parents[1]
        cfg = load_accessibility_config(repo_root / "configs" / "accessibility.defaults.toml")
        self.assertEqual(cfg.api.base_url, "https://www.rejseplanen.dk/api")
        self.assertTrue(cfg.static_dir.name == "accessibility")
        self.assertEqual(cfg.frontend.default_sort_by, "quality_desc")
        self.assertEqual(cfg.frontend.overlay_min_lat, 55.55)

    def test_reachability_cache_key_is_bucketed_and_stable(self):
        query = ReachabilityQuery(
            origin_key="8600646",
            depart_at_local="2026-03-16T08:32:00",
            max_minutes=45,
            modes=("metro", "train", "bus"),
            max_changes=2,
        )
        key = build_reachability_cache_key(query)
        self.assertIn("origin=8600646", key)
        self.assertIn("time=2026-03-16T08:30", key)
        self.assertIn("modes=bus,metro,train", key)

    def test_location_search_cache_key_is_normalized(self):
        key = build_location_search_cache_key("  Nørreport   St  ", 8)
        self.assertEqual(key, "location:v1:nørreport st:8")

    def test_cache_round_trip(self):
        repo_root = Path(__file__).resolve().parents[1]
        cache = JsonCache(repo_root / "data" / "cache" / "accessibility")
        cache.set("test:key", {"items": [1]})
        result = cache.get("test:key", ttl_sec=60)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.payload["items"], [1])

    def test_client_param_builders_use_config(self):
        api_cfg = RejseplanenAPIConfig(
            base_url="https://www.rejseplanen.dk/api",
            request_timeout_sec=15,
            location_search_limit=8,
            max_minutes_default=45,
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
            reachability_modes_param="products",
            mode_separator=",",
        )
        location_params = build_location_search_params("Norreport", 8, api_cfg, "KEY")
        self.assertEqual(location_params["input"], "Norreport")
        self.assertEqual(location_params["maxNo"], "8")
        reachability_params = build_reachability_params(
            origin=OriginRef(id="8600646", type="stop", lat=55.68, lon=12.57),
            query=ReachabilityQuery(
                origin_key="8600646",
                depart_at_local="2026-03-16T08:32:00",
                max_minutes=45,
                modes=("train", "bus"),
                max_changes=2,
            ),
            api_cfg=api_cfg,
            access_id="KEY",
        )
        self.assertEqual(reachability_params["originId"], "8600646")
        self.assertEqual(reachability_params["date"], "2026-03-16")
        self.assertEqual(reachability_params["time"], "08:32")
        self.assertEqual(reachability_params["duration"], "45")
        self.assertEqual(reachability_params["maxChange"], "2")
        self.assertEqual(reachability_params["products"], "127")

    def test_products_mask_supports_current_mode_filters(self):
        mask = _products_mask_for_modes(("train", "metro", "bus"))
        self.assertEqual(mask, 1151)

    def test_extract_location_id_prefers_extid(self):
        item = {
            "id": "A=1@O=Nørreport St.@L=8600646@",
            "extId": "8600646",
        }
        self.assertEqual(_extract_location_id(item), "8600646")

    def test_extract_primary_product_normalizes_walk_label(self):
        item = {
            "productAtStop": [
                {"name": "-Fußweg-", "catOut": ""}
            ]
        }
        self.assertEqual(_extract_primary_product(item), ("Walk link", "Walk"))

    def test_line_reliability_lookup_loads_current_artifact(self):
        repo_root = Path(__file__).resolve().parents[1]
        lookup = load_line_reliability_lookup(repo_root / "data" / "analysis" / "week3_line_reliability_rank.csv")
        self.assertIn("Re 4516", lookup)
        self.assertEqual(lookup["Re 4516"]["risk_p95_delay_sec"], 780)

    def test_paginate_reachability_results_applies_window_and_page(self):
        stops = [
            {"id": f"s{i}", "name": f"Stop {i}", "travel_time_min": i}
            for i in range(1, 31)
        ]
        paged = paginate_reachability_results(stops, page=2, per_page=5, max_result_window=12)
        self.assertEqual(paged["stats"]["total_reachable_stop_count"], 30)
        self.assertEqual(paged["stats"]["clipped_reachable_stop_count"], 12)
        self.assertEqual(paged["stats"]["returned_stop_count"], 5)
        self.assertEqual(paged["stats"]["total_pages"], 3)
        self.assertEqual(paged["reachable_stops"][0]["id"], "s6")
        self.assertEqual(sum(paged["stats"]["bucket_counts"].values()), 12)

    def test_reliability_summary_compares_scheduled_and_robust_accessibility(self):
        rows = [
            {"id": "a", "travel_time_min": 20, "risk_p95_delay_sec": 60, "evidence_level": "high", "reliability_band": "stable"},
            {"id": "b", "travel_time_min": 44, "risk_p95_delay_sec": 180, "evidence_level": "medium", "reliability_band": "at-risk"},
            {"id": "c", "travel_time_min": 48, "risk_p95_delay_sec": 0, "evidence_level": "summary", "reliability_band": "leading"},
        ]
        summary = summarize_reachability_window(rows, max_minutes=45)
        self.assertEqual(summary["scheduled_accessible_count"], 2)
        self.assertEqual(summary["robust_accessible_count"], 1)
        self.assertEqual(summary["accessibility_loss_count"], 1)
        self.assertEqual(summary["high_confidence_count"], 3)
        self.assertEqual(summary["at_risk_or_critical_count"], 1)

    def test_apply_result_controls_sorts_and_filters_service_quality(self):
        rows = [
            {"id": "a", "name": "A", "travel_time_min": 20, "changes": 1, "reliability_band": "stable", "risk_p95_delay_sec": 120},
            {"id": "b", "name": "B", "travel_time_min": 18, "changes": 0, "reliability_band": "leading", "risk_p95_delay_sec": 60},
            {"id": "c", "name": "C", "travel_time_min": 11, "changes": 0, "reliability_band": "critical", "risk_p95_delay_sec": 600},
        ]
        quality_sorted = apply_result_controls(
            rows,
            sort_by="quality_desc",
            reliability_filter="all",
            bucket_filter="all",
            direct_only=False,
        )
        self.assertEqual([row["id"] for row in quality_sorted], ["b", "a", "c"])
        direct_only = apply_result_controls(
            rows,
            sort_by="travel_time_asc",
            reliability_filter="all",
            bucket_filter="0-15",
            direct_only=True,
        )
        self.assertEqual([row["id"] for row in direct_only], ["c"])

    def test_filter_overlays_to_bounds_limits_to_copenhagen_window(self):
        overlays = {
            "hubs": [
                {"name": "CPH", "lat": 55.68, "lon": 12.57},
                {"name": "Odense", "lat": 55.36, "lon": 10.39},
            ],
            "vulnerable_nodes": [
                {"name": "CPH node", "lat": 55.73, "lon": 12.50},
                {"name": "Jutland node", "lat": 56.56, "lon": 9.02},
            ],
        }
        filtered = filter_overlays_to_bounds(
            overlays,
            min_lat=55.55,
            max_lat=55.82,
            min_lon=12.05,
            max_lon=12.72,
        )
        self.assertEqual([item["name"] for item in filtered["hubs"]], ["CPH"])
        self.assertEqual([item["name"] for item in filtered["vulnerable_nodes"]], ["CPH node"])

    def test_scaffold_files_exist(self):
        repo_root = Path(__file__).resolve().parents[1]
        expected = [
            repo_root / "docs" / "accessibility_product_plan.md",
            repo_root / "configs" / "accessibility.defaults.toml",
            repo_root / "web" / "accessibility" / "index.html",
            repo_root / "web" / "accessibility" / "app.js",
            repo_root / "web" / "accessibility" / "styles.css",
        ]
        for path in expected:
            self.assertTrue(path.exists(), str(path))


if __name__ == "__main__":
    unittest.main()
