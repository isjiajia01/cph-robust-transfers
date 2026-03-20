import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from src.gtfs_ingest.parse import extract_csv_from_zip


class GtfsParseTest(unittest.TestCase):
    def test_missing_required_file(self):
        with tempfile.TemporaryDirectory() as td:
            zip_path = Path(td) / "bad.zip"
            with ZipFile(zip_path, "w") as zf:
                zf.writestr("stops.txt", "stop_id,stop_name\n1,A\n")
            with self.assertRaises(FileNotFoundError):
                extract_csv_from_zip(zip_path, Path(td) / "out")


if __name__ == "__main__":
    unittest.main()
