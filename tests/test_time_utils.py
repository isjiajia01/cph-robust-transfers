import unittest

from src.common.time_utils import hhmmss_to_seconds


class TimeUtilsTest(unittest.TestCase):
    def test_over_24h(self):
        self.assertEqual(hhmmss_to_seconds("25:10:05"), 90605)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            hhmmss_to_seconds("10:00")


if __name__ == "__main__":
    unittest.main()
