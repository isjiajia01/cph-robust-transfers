import tempfile
import unittest
from pathlib import Path

from src.robustness.risk_model import ModeLevelRiskModel
from src.robustness.router import RouterConfig, _load_router_config, run_router


class PhaseCOptimizationTest(unittest.TestCase):
    def test_mode_level_risk_model_uses_mode_hour_then_mode_then_global(self):
        rows = []
        for delay in range(10, 310, 10):
            rows.append(
                {
                    "line": "L_small",
                    "mode": "train",
                    "delay_sec": str(delay),
                    "hour_cph": "8",
                }
            )
        for delay in range(20, 1220, 20):
            rows.append(
                {
                    "line": "L_mode",
                    "mode": "train",
                    "delay_sec": str(delay),
                    "hour_cph": "12",
                }
            )
        for delay in range(5, 605, 5):
            rows.append(
                {
                    "line": "L_other",
                    "mode": "bus",
                    "delay_sec": str(delay),
                    "hour_cph": "17",
                }
            )

        model = ModeLevelRiskModel(rows, n_mode_hour_min=20, n_mode_min=40, bootstrap_iters=10, seed=7)

        est_mode_hour = model.estimate(line="UNKNOWN", mode="train", hour_cph=8, stop_type="hub", context={})
        est_mode = model.estimate(line="UNKNOWN", mode="train", hour_cph=10, stop_type="hub", context={})
        est_global = model.estimate(line="UNKNOWN", mode="tram", hour_cph=9, stop_type="local", context={})

        self.assertEqual(est_mode_hour.source_level, "mode_hour")
        self.assertEqual(est_mode.source_level, "mode")
        self.assertEqual(est_global.source_level, "global")
        self.assertIn('"source_level": "mode_hour"', est_mode_hour.delay_distribution)

    def test_router_config_loads_from_toml(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "router.defaults.toml"
            path.write_text(
                "[router]\n"
                "slack_min = 7.5\n"
                "minimum_transfer_time_min = 4.0\n"
                "walk_time_assumption_min = 2.5\n"
                'missed_transfer_rule = "custom_rule"\n',
                encoding="utf-8",
            )

            cfg = _load_router_config(path)

            self.assertEqual(cfg.slack_min, 7.5)
            self.assertEqual(cfg.minimum_transfer_time_min, 4.0)
            self.assertEqual(cfg.walk_time_assumption_min, 2.5)
            self.assertEqual(cfg.missed_transfer_rule, "custom_rule")

    def test_router_outputs_phase_c_contract(self):
        rows = [
            {"line": "IC 818", "mode": "train", "delay_sec": "120", "hour_cph": "8"},
            {"line": "IC 818", "mode": "train", "delay_sec": "180", "hour_cph": "8"},
            {"line": "IC 818", "mode": "train", "delay_sec": "240", "hour_cph": "8"},
            {"line": "Re 1049", "mode": "train", "delay_sec": "60", "hour_cph": "8"},
        ] * 80
        model = ModeLevelRiskModel(rows, n_line_min=50, n_mode_min=50, bootstrap_iters=10, seed=11)
        cfg = RouterConfig()
        candidates = [
            {
                "od_id": "CPH_H_CPH_AIRPORT",
                "depart_ts_cph": "2026-03-02T08:15:00+01:00",
                "path_id": "path_a",
                "line": "IC 818",
                "mode": "train",
                "travel_time_min": "24",
                "transfers": "1",
                "stop_type": "hub",
            }
        ]

        out = run_router(candidates, model, config=cfg)

        self.assertEqual(len(out), 1)
        row = out[0]
        for key in (
            "od_id",
            "depart_ts_cph",
            "path_id",
            "travel_time_min",
            "transfers",
            "miss_prob",
            "cvar95_min",
            "evidence_level",
            "sample_size_effective",
            "risk_model_version",
            "hour_cph",
            "stop_type",
            "source_level",
            "delay_distribution",
            "router_config_version",
            "context_json",
        ):
            self.assertIn(key, row)
        self.assertEqual(row["stop_type"], "hub")
        self.assertEqual(row["hour_cph"], 8)

    def test_small_sample_withholds_p95_ci_and_marks_low_evidence(self):
        rows = [
            {"line": "L1", "mode": "bus", "delay_sec": "60", "hour_cph": "9"},
            {"line": "L1", "mode": "bus", "delay_sec": "120", "hour_cph": "9"},
            {"line": "L1", "mode": "bus", "delay_sec": "180", "hour_cph": "9"},
        ]
        model = ModeLevelRiskModel(rows, n_mode_hour_min=2, n_mode_min=10, bootstrap_iters=10, seed=5)

        est = model.estimate(line="L1", mode="bus", hour_cph=9, stop_type="local", context={})

        self.assertEqual(est.p95_ci_low, 0)
        self.assertEqual(est.p95_ci_high, 0)
        self.assertEqual(est.evidence_level, "low")
        self.assertIn("withheld", est.uncertainty_note)


if __name__ == "__main__":
    unittest.main()
