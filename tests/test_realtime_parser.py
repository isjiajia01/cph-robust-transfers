import unittest

from src.realtime.parser import parse_board_response


class RealtimeParserTest(unittest.TestCase):
    def test_parse_single_departure_dict(self):
        payload = {
            "Departure": {
                "date": "2026-03-02",
                "time": "10:00",
                "rtDate": "2026-03-02",
                "rtTime": "10:02",
                "stopid": "123",
                "name": "A",
                "JourneyDetailRef": {"ref": "abc|1"},
            }
        }
        rows = parse_board_response(payload, "2026-03-02T09:59:00Z", "run1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["api_station_id"], "123")
        self.assertEqual(rows[0]["journey_ref"], "abc|1")
        self.assertEqual(rows[0]["delay_sec"], 120)


if __name__ == "__main__":
    unittest.main()
