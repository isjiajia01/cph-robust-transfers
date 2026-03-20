import unittest
from unittest import mock

from src.app import cli as app_cli
from src.optimization import api as optimization_api
from src.optimization import cli as optimization_cli


class TemplateCliTest(unittest.TestCase):
    def test_app_cli_parser_accepts_template_commands(self):
        parser = app_cli.build_parser()
        args = parser.parse_args(["realtime-collector"])
        self.assertEqual(args.command, "realtime-collector")
        dashboard_args = parser.parse_args(["results-dashboard"])
        self.assertEqual(dashboard_args.command, "results-dashboard")
        accessibility_args = parser.parse_args(["accessibility-build-static"])
        self.assertEqual(accessibility_args.command, "accessibility-build-static")

    def test_app_cli_dispatches_results_dashboard_without_forwarding_subcommand(self):
        with mock.patch("src.app.results_dashboard.main", return_value=0) as dashboard_main:
            rc = app_cli.main(["results-dashboard"])

        self.assertEqual(rc, 0)
        dashboard_main.assert_called_once_with([])

    def test_optimization_cli_parser_accepts_template_commands(self):
        parser = optimization_cli.build_parser()
        args = parser.parse_args(["risk-model"])
        self.assertEqual(args.command, "risk-model")

    def test_optimization_api_exposes_current_project_types(self):
        self.assertIsNotNone(optimization_api.get_risk_model_class())
        self.assertIsNotNone(optimization_api.get_risk_estimate_class())
        self.assertTrue(callable(optimization_api.run_router))


if __name__ == "__main__":
    unittest.main()
