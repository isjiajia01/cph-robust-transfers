import unittest

from src.app import realtime_pipeline, static_pipeline
from src.optimization import risk_model, robustness, router


class TemplateBridgeTest(unittest.TestCase):
    def test_app_bridges_import(self):
        self.assertTrue(callable(realtime_pipeline.collector_main))
        self.assertTrue(callable(static_pipeline.gtfs_download_main))

    def test_optimization_bridges_import(self):
        self.assertTrue(callable(router.run_router))
        self.assertTrue(callable(risk_model.main))
        self.assertTrue(callable(robustness.simulate_failures_main))


if __name__ == "__main__":
    unittest.main()
